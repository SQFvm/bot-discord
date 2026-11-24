//! Dynamically loaded Rust bindings for SQF-VM's `src/export/sqfvm.h`.
//!
//! ```no_run
//! use sqfvm::{Mode, Operators, SqfVm};
//! use std::{path::Path, time::Duration};
//!
//! # fn main() -> Result<(), Box<dyn std::error::Error>> {
//! // SAFETY: the operator supplied a trusted build of libsqfvm.
//! let mut vm = unsafe { SqfVm::load(Path::new("/opt/sqfvm/libsqfvm.so")) }?;
//! let mut instance = vm.instance(Operators::Full, Duration::from_secs(10), |_, bytes| {
//!     println!("{}", String::from_utf8_lossy(bytes));
//! })?;
//! instance.load_config("class Example {};")?;
//! instance.call(Mode::Sqf, "1 + 2")?;
//! # Ok(()) }
//! ```

use libloading::Library;
use std::{
    any::Any,
    ffi::{c_char, c_void},
    panic::{AssertUnwindSafe, catch_unwind, resume_unwind},
    path::Path,
    ptr::{self, NonNull},
    slice,
    time::Duration,
};
use thiserror::Error;

type Callback = unsafe extern "C" fn(*mut c_void, *mut c_void, i32, *const c_char, u32);
type Create = unsafe extern "C" fn(*mut c_void, Callback, f32) -> *mut c_void;
type Destroy = unsafe extern "C" fn(*mut c_void);
type LoadConfig = unsafe extern "C" fn(*mut c_void, *const c_char, u32) -> i32;
type Call = unsafe extern "C" fn(*mut c_void, *mut c_void, c_char, *const c_char, u32) -> i32;
type StatusFn = unsafe extern "C" fn(*mut c_void) -> i32;

pub enum Operators {
    Full,
    Basic,
    Empty,
}

#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    Sqf = b's',
    Sqc = b'c',
    SqfToSqc = b'1',
    Assembly = b'a',
    Preprocess = b'p',
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Status {
    Ready,
    Halted,
    Running,
    HaltedError,
    Evaluating,
    Unknown(i32),
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum Error {
    #[error("SQF-VM could not create an instance")]
    Create,
    #[error("invalid SQF-VM instance")]
    InvalidInstance,
    #[error("preprocessing failed")]
    Preprocess,
    #[error("parsing failed")]
    Parse,
    #[error("the instance is already running")]
    AlreadyRunning,
    #[error("the library does not support this execution mode")]
    UnsupportedMode,
    #[error("execution failed")]
    Execution,
    #[error("unexpected SQF-VM return code {0}")]
    Unknown(i32),
    #[error("input exceeds the native API's 32-bit byte length")]
    InputTooLong,
    #[error("timeout is outside the native millisecond range")]
    InvalidTimeout,
}

fn check(code: i32) -> Result<(), Error> {
    match code {
        0 => Ok(()),
        -1 => Err(Error::InvalidInstance),
        -2 => Err(Error::Preprocess),
        -3 => Err(Error::Parse),
        -4 => Err(Error::AlreadyRunning),
        -5 => Err(Error::UnsupportedMode),
        -6 => Err(Error::Execution),
        other => Err(Error::Unknown(other)),
    }
}

pub struct SqfVm {
    create: Create,
    create_basic: Create,
    create_empty: Create,
    destroy: Destroy,
    config: LoadConfig,
    call: Call,
    status: StatusFn,
    _library: Library,
}

impl SqfVm {
    /// Loads all exports before publishing the library to callers.
    ///
    /// # Safety
    /// The library and its dependencies must be trusted and implement the SQF-VM
    /// C ABI, including synchronous callbacks with valid byte buffers.
    pub unsafe fn load(path: &Path) -> Result<Self, libloading::Error> {
        unsafe {
            let library = Library::new(path)?;
            Ok(Self {
                create: *library.get(b"sqfvm_create_instance\0")?,
                create_basic: *library.get(b"sqfvm_create_instance_basic\0")?,
                create_empty: *library.get(b"sqfvm_create_instance_empty\0")?,
                destroy: *library.get(b"sqfvm_destroy_instance\0")?,
                config: *library.get(b"sqfvm_load_config\0")?,
                call: *library.get(b"sqfvm_call\0")?,
                status: *library.get(b"sqfvm_status\0")?,
                _library: library,
            })
        }
    }

    /// The logger receives the native severity (-1 for results, 0–5 for logs)
    /// and exactly the bytes supplied by the VM. Zero disables the VM timeout.
    pub fn instance<F: FnMut(i32, &[u8])>(
        &mut self,
        operators: Operators,
        timeout: Duration,
        logger: F,
    ) -> Result<Instance<'_, F>, Error> {
        let seconds = timeout.as_secs_f32();
        if (!timeout.is_zero() && timeout < Duration::from_millis(1))
            || seconds * 1000.0 >= i64::MAX as f32
        {
            return Err(Error::InvalidTimeout);
        }
        let create = match operators {
            Operators::Full => self.create,
            Operators::Basic => self.create_basic,
            Operators::Empty => self.create_empty,
        };
        let mut callbacks = Box::new(Callbacks {
            logger,
            panic: None,
        });
        // The allocation stays at a stable address until after destroy returns.
        let user_data = ptr::from_mut(callbacks.as_mut()).cast();
        let raw =
            NonNull::new(unsafe { create(user_data, log::<F>, seconds) }).ok_or(Error::Create)?;
        let mut instance = Instance {
            raw,
            vm: self,
            callbacks,
        };
        instance.callbacks.check_panic();
        Ok(instance)
    }
}

struct Callbacks<F> {
    logger: F,
    panic: Option<Box<dyn Any + Send>>,
}

impl<F> Callbacks<F> {
    fn check_panic(&mut self) {
        if let Some(panic) = self.panic.take() {
            resume_unwind(panic);
        }
    }
}

unsafe extern "C" fn log<F: FnMut(i32, &[u8])>(
    data: *mut c_void,
    _: *mut c_void,
    severity: i32,
    message: *const c_char,
    len: u32,
) {
    // data is the boxed state supplied at creation. The C API calls it
    // synchronously and lends message for the duration of this callback.
    let state = unsafe { &mut *data.cast::<Callbacks<F>>() };
    if state.panic.is_none() {
        let bytes = if len == 0 {
            &[]
        } else {
            unsafe { slice::from_raw_parts(message.cast(), len as usize) }
        };
        state.panic = catch_unwind(AssertUnwindSafe(|| (state.logger)(severity, bytes))).err();
    }
}

pub struct Instance<'vm, F> {
    raw: NonNull<c_void>,
    vm: &'vm mut SqfVm,
    callbacks: Box<Callbacks<F>>,
}

impl<F> Instance<'_, F> {
    pub fn call(&mut self, mode: Mode, code: &str) -> Result<(), Error> {
        let len = code.len().try_into().map_err(|_| Error::InputTooLong)?;
        let result = unsafe {
            (self.vm.call)(
                self.raw.as_ptr(),
                ptr::null_mut(),
                mode as c_char,
                code.as_ptr().cast(),
                len,
            )
        };
        self.callbacks.check_panic();
        check(result)
    }

    pub fn load_config(&mut self, code: &str) -> Result<(), Error> {
        let len = code.len().try_into().map_err(|_| Error::InputTooLong)?;
        let result = unsafe { (self.vm.config)(self.raw.as_ptr(), code.as_ptr().cast(), len) };
        self.callbacks.check_panic();
        check(result)
    }

    pub fn status(&self) -> Result<Status, Error> {
        match unsafe { (self.vm.status)(self.raw.as_ptr()) } {
            -1 => Err(Error::InvalidInstance),
            0 => Ok(Status::Ready),
            1 => Ok(Status::Halted),
            2 => Ok(Status::Running),
            3 => Ok(Status::HaltedError),
            4 => Ok(Status::Evaluating),
            other => Ok(Status::Unknown(other)),
        }
    }
}

impl<F> Drop for Instance<'_, F> {
    fn drop(&mut self) {
        // Both the library and callbacks outlive the native instance.
        unsafe { (self.vm.destroy)(self.raw.as_ptr()) };
    }
}
