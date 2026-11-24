use sqfvm::{Error, Mode, Operators, SqfVm, Status};
use std::{env, path::PathBuf, time::Duration};

#[test]
#[ignore = "set SQFVM_LIB_PATH to an SQC-enabled libsqfvm"]
fn native_api() {
    let path = PathBuf::from(env::var_os("SQFVM_LIB_PATH").expect("SQFVM_LIB_PATH"))
        .canonicalize()
        .unwrap();
    // SAFETY: the operator selects a trusted native build for this test.
    let mut vm = unsafe { SqfVm::load(&path) }.unwrap();
    for ops in [Operators::Basic, Operators::Empty, Operators::Full] {
        let mut instance = vm.instance(ops, Duration::from_secs(2), |_, _| {}).unwrap();
        assert_eq!(instance.status(), Ok(Status::Ready));
        instance
            .load_config("class RustBindingTest { value = 42; };")
            .unwrap();
    }
    for (mode, source, expected) in [
        (Mode::Sqf, "6 * 7", "42"),
        (Mode::Preprocess, "#define WORD café\nWORD", "café"),
        (Mode::Sqc, "6 * 7;", "42"),
        (Mode::SqfToSqc, "6 * 7", "7"),
    ] {
        let mut output = Vec::new();
        let mut instance = vm
            .instance(Operators::Full, Duration::from_secs(2), |_, message| {
                output.extend_from_slice(message);
            })
            .unwrap();
        instance.call(mode, source).unwrap();
        drop(instance);
        assert!(
            String::from_utf8_lossy(&output).contains(expected),
            "{mode:?}: {output:?}"
        );
    }
    {
        let mut messages = Vec::new();
        let mut instance = vm
            .instance(Operators::Full, Duration::from_secs(2), |_, message| {
                messages.extend_from_slice(message);
            })
            .unwrap();
        instance.call(Mode::Assembly, "PUSH 42").unwrap();
        // The assembly parser can recover and report errors via the logger.
        let _ = instance.call(Mode::Assembly, "PUSH");
        drop(instance);
        assert!(String::from_utf8_lossy(&messages).contains("Parse Error"));
    }
    let mut diagnostics = Vec::new();
    let mut instance = vm
        .instance(Operators::Full, Duration::from_secs(2), |_, message| {
            diagnostics.extend_from_slice(message);
        })
        .unwrap();
    assert_eq!(instance.call(Mode::Sqf, "1 +"), Err(Error::Parse));
    drop(instance);
    assert!(!diagnostics.is_empty());
}
