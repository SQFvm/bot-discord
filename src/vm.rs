use crate::commands::{clipped, mode_name};
use anyhow::{Context, Result, bail, ensure};
use sqfvm::{Mode, Operators, SqfVm};
use std::{
    env, fs,
    io::{self, Read},
    path::{Path, PathBuf},
    process::Stdio,
    time::Duration,
};
use tokio::{io::AsyncWriteExt, process::Command, sync::Mutex, time::timeout};

const VM_TIMEOUT: Duration = Duration::from_secs(10);
const OUTPUT_BYTES: usize = 16 * 1024;
pub const EVAL_ERROR: u8 = 2;

pub struct Runtime {
    source: PathBuf,
    build: PathBuf,
    library: PathBuf,
    gate: Mutex<()>,
}

fn library_path(build: &Path) -> PathBuf {
    let filename = format!("libsqfvm{}", env::consts::DLL_SUFFIX);
    let flat = build.join(&filename);
    let release = build.join("Release").join(&filename);
    if release.is_file() || (cfg!(windows) && !flat.is_file()) {
        release
    } else {
        flat
    }
}

impl Runtime {
    pub fn from_env() -> Self {
        let source = env::var_os("SQFVM_SOURCE_DIR")
            .map_or_else(|| PathBuf::from("../runtime"), PathBuf::from);
        let build = env::var_os("SQFVM_BUILD_DIR")
            .map_or_else(|| PathBuf::from("target/sqfvm"), PathBuf::from);
        let library =
            env::var_os("SQFVM_LIB_PATH").map_or_else(|| library_path(&build), PathBuf::from);
        Self {
            source,
            build,
            library,
            gate: Mutex::new(()),
        }
    }

    pub fn library(&self) -> &Path {
        &self.library
    }

    pub async fn eval(&self, mode: Mode, source: &str) -> Result<String> {
        let _guard = self.gate.lock().await;
        let (_, output) = Self::worker(&self.library, mode, source).await?;
        Ok(output)
    }

    async fn worker(library: &Path, mode: Mode, source: &str) -> Result<(bool, String)> {
        ensure!(
            library.is_file(),
            "SQF-VM is unavailable. An admin can run !rebuild."
        );
        // A fresh process releases the DLL after every call and keeps native VM
        // crashes or a stalled preprocessor out of the Discord gateway process.
        let mut child = Command::new(env::current_exe()?)
            .args(["--eval", mode_name(mode)])
            .arg(library)
            .env_remove("DISCORD_TOKEN")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true)
            .spawn()
            .context("starting SQF-VM worker")?;
        let output = timeout(VM_TIMEOUT + Duration::from_secs(3), async {
            let mut stdin = child.stdin.take().context("opening worker stdin")?;
            stdin.write_all(source.as_bytes()).await?;
            drop(stdin);
            Ok::<_, anyhow::Error>(child.wait_with_output().await?)
        })
        .await
        .context("SQF-VM exceeded its time limit")??;
        if !output.status.success() && output.status.code() != Some(EVAL_ERROR.into()) {
            let reason = String::from_utf8_lossy(&output.stderr);
            bail!(
                "SQF-VM worker exited with {}. {}",
                output.status,
                clipped(reason.trim(), 500)
            );
        }
        Ok((output.status.success(), String::from_utf8(output.stdout)?))
    }

    pub async fn rebuild(&self) -> Result<()> {
        let _guard = self.gate.lock().await;
        checked(
            Command::new("git")
                .arg("-C")
                .arg(&self.source)
                .args(["pull", "--ff-only"]),
        )
        .await?;
        checked(
            Command::new("cmake")
                .arg("-S")
                .arg(&self.source)
                .arg("-B")
                .arg(&self.build)
                .args([
                    "-DCMAKE_BUILD_TYPE=Release",
                    "-DSQFVM_ENABLE_SQC_SUPPORT=ON",
                ]),
        )
        .await?;
        checked(Command::new("cmake").arg("--build").arg(&self.build).args([
            "--config",
            "Release",
            "--target",
            "libsqfvm",
            "--parallel",
            "6",
        ]))
        .await?;
        let built = library_path(&self.build)
            .canonicalize()
            .context("locating built library")?;
        let (works, response) = Self::worker(&built, Mode::Sqc, "1 + 1;").await?;
        ensure!(works, "rebuilt SQF-VM failed its SQC check: {response}");
        if self.library.canonicalize().ok().as_ref() != Some(&built) {
            let destination = std::path::absolute(&self.library)?;
            let mut staging = tempfile::NamedTempFile::new_in(
                destination.parent().context("library directory")?,
            )?;
            io::copy(&mut fs::File::open(built)?, staging.as_file_mut())?;
            staging.persist(destination)?;
        }
        Ok(())
    }
}

async fn checked(cmd: &mut Command) -> Result<()> {
    let program = cmd.as_std().get_program().to_string_lossy().into_owned();
    let status = cmd
        .env_remove("DISCORD_TOKEN")
        .stdin(Stdio::null())
        .kill_on_drop(true)
        .status()
        .await
        .with_context(|| format!("starting {program}"))?;
    ensure!(
        status.success(),
        "{program} exited with {status}. See the bot log for build output."
    );
    Ok(())
}

/// The worker also provides a token-free local entry point for the interpreter.
pub fn run_worker(path: &Path, mode: Mode) -> Result<u8> {
    let mut source = String::new();
    io::stdin().read_to_string(&mut source)?;
    let path = path
        .canonicalize()
        .with_context(|| format!("locating {}", path.display()))?;
    // SAFETY: the deployment operator selects the SQF-VM library. Discord
    // messages supply only the mode and source, never a library path.
    let mut vm = unsafe { SqfVm::load(&path) }.context("loading SQF-VM exports")?;
    let mut bytes = Vec::new();
    let mut messages = 0usize;
    let mut truncated = false;
    let mut instance = vm.instance(Operators::Full, VM_TIMEOUT, |_, message| {
        if messages > 0 && bytes.len() < OUTPUT_BYTES {
            bytes.push(b'\n');
        }
        messages += 1;
        let len = message.len().min(OUTPUT_BYTES - bytes.len());
        bytes.extend_from_slice(&message[..len]);
        truncated |= len < message.len();
    })?;
    let result = instance.call(mode, &source);
    drop(instance);
    print!("{}", String::from_utf8_lossy(&bytes));
    if truncated {
        print!("…");
    }
    if let Err(error) = result {
        print!("\nError: {error}");
        return Ok(EVAL_ERROR);
    } else if mode == Mode::SqfToSqc && messages == 0 {
        // The native API returns success without a callback in SQC-disabled builds.
        print!("SQC translation is unavailable in this build of SQF-VM.");
        return Ok(EVAL_ERROR);
    }
    Ok(0)
}
