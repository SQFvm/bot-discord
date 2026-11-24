# SQF-VM Discord bot

The bot evaluates SQF snippets and looks up Arma scripting commands on the Bohemia Interactive Community Wiki. The Cargo workspace contains the Discord application and a reusable [SQF-VM bindings crate](crates/sqfvm/src/lib.rs).

## Build and run

Use Rust 1.88 or later. To build the native library, use CMake and a C++17 compiler with an existing [SQF-VM runtime checkout](https://github.com/SQFvm/runtime). These commands assume that checkout is at `../runtime`.

```sh
cmake -S ../runtime -B target/sqfvm -DCMAKE_BUILD_TYPE=Release -DSQFVM_ENABLE_SQC_SUPPORT=ON
cmake --build target/sqfvm --config Release --target libsqfvm
cargo build --release --locked
```

The bot loads `libsqfvm.so` on Linux, `libsqfvm.dylib` on macOS, or `Release/libsqfvm.dll` with Visual Studio on Windows, relative to the native build directory. Set `SQFVM_LIB_PATH` to use an existing compatible library. SQC evaluation and translation require an SQC-enabled build.

In the [Discord Developer Portal](https://discord.com/developers/applications), enable **Message Content Intent** under **Bot**. Invite the bot with **View Channels**, **Send Messages**, and **Embed Links** permissions. Set `DISCORD_TOKEN` in the process environment, then start the bot from this checkout.

```sh
cargo run --release --locked
```

To check the interpreter locally, pipe code to the same worker the bot uses. This works without a Discord token.

```sh
echo '6 * 7' | cargo run --quiet --locked -- --eval sqf
```

## Commands

| Command | Result |
| --- | --- |
| `!sqf 6 * 7` | Evaluates SQF and displays the VM output. |
| `!sqc 6 * 7;` | Evaluates SQC. |
| `!sqf2sqc hint "hello"` | Translates SQF into SQC. |
| `!assembly <code>` | Executes SQF-VM assembly. |
| `!preprocess <code>` | Expands preprocessor directives. |
| `!biki hint` | Shows the Biki description and page link. |
| `!biki_full hint` | Adds syntax, parameters, return values, examples, and related commands. |
| `!biki_sqc hint` | Shows the full entry with examples translated to SQC. |
| `!help [command]` | Sends command help by DM when possible. |

A direct message or a mention evaluates plain text as SQF. A fenced code block tagged `sqf`, `sqc`, `sqf2sqc`, `assembly`, or `preprocess` selects its mode. In channels whose names start with `sqf` or `sqc`, a tagged block also works without a mention. Each evaluation gets a fresh VM instance, a ten-second native execution limit, and a worker process with a thirteen-second deadline.

## Configuration and deployment

When migrating from `settings/local.py`, move the bot token, username, and admin IDs into the service environment. Set native compiler overrides such as `CC` and `CXX` there as well.

| Variable | Default or purpose |
| --- | --- |
| `DISCORD_TOKEN` | Required for the Discord gateway. |
| `DISCORD_BOT_NAME` | Defaults to `SQF`. An empty value preserves the account's current username. |
| `DISCORD_ADMINS` | Comma-separated Discord user IDs. Defaults to the original admin, `105784568346324992`. An empty value disables admin commands. |
| `SQFVM_SOURCE_DIR` | Existing runtime checkout, default `../runtime`. |
| `SQFVM_BUILD_DIR` | CMake build directory, default `target/sqfvm` inside the bot checkout. |
| `SQFVM_LIB_PATH` | Path to the shared library. Defaults to the platform-specific build output described above. |

`!rebuild` waits for the current evaluation, fast-forwards the runtime checkout from its configured upstream, builds `libsqfvm` with SQC enabled, and runs a native smoke check. If the configured library lives elsewhere, the bot installs the checked build at that path. The command requires Git and CMake on the service's `PATH`. Biki lookups and help also work while the library is unavailable.

`!restart` closes the Discord connection and exits with status 75. On Unix, `sh start_production.sh` supervises the process, fast-forwards the bot checkout from its upstream, and builds and starts the release binary. Ctrl+C stops the bot. Runtime and build diagnostics go to the process logs. A public deployment should run under a dedicated, least-privileged account because the native worker inherits the service account's operating-system permissions.

## CI and release packages

GitHub Actions builds Linux x64 and Windows x64 packages on pushes and pull requests. Each package includes the bot and the SQC-enabled native library used in its integration tests. The workflow extracts each archive and runs an SQC calculation before uploading it. Pushing a `v*` tag publishes those archives as a GitHub Release after all checks pass.

To run a downloaded package, extract the archive, change into the extracted directory, set `DISCORD_TOKEN`, and start `./sqf-discord` on Linux or `.\sqf-discord.exe` on Windows.

## Rust bindings and tests

Add the `sqfvm` crate as a Cargo path dependency to use it independently. It loads the native C ABI at runtime, supports full, basic, and empty operator sets, and exposes configuration loading, status, and the five call modes. A logger receives the severity and message bytes for each native callback. Dropping the instance releases it before its library can unload.

```sh
cargo test --workspace --locked
cargo doc -p sqfvm --no-deps --open
```

With `SQFVM_LIB_PATH` set to a trusted SQC-enabled build, run the native integration test. The Biki smoke test uses the public wiki API.

```sh
cargo test -p sqfvm --test native --locked -- --ignored
cargo test -p sqf-discord --locked live_page -- --ignored
```
