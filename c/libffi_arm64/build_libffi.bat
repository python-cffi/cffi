@echo off
goto :Run
 
:Usage
echo.
echo Before running prepare_libffi.bat
echo .
echo   LIBFFI_SOURCE environment variable must be set to the location of libffi source
echo   Source can be checked out from https://github.com/libffi/libffi
echo.
echo   Cygwin needs to be installed (Invoke with --install-cygwin to install)
echo.  
echo.  Visual Studio 2017 or newer with ARM64 toolchain needs to be installed
:Run
set INSTALL_CYGWIN=
 
:CheckOpts
if "%1"=="" goto :CheckOptsDone
if /I "%1"=="-?" goto :Usage
if /I "%1"=="--install-cygwin" (set INSTALL_CYGWIN=1) & shift & goto :CheckOpts
goto :Usage
 
:CheckOptsDone
 
if "%INSTALL_CYGWIN%"=="1" call :InstallCygwin
 
REM Set build variables
 
set BUILD=i686-pc-cygwin
set HOST=aarch64-w64-cygwin
if NOT DEFINED SH if exist c:\cygwin\bin\sh.exe set SH=c:\cygwin\bin\sh.exe
 
REM Initialise ARM64 build environment
 
if NOT DEFINED VCVARSALL (
  for /F "tokens=*" %%i in ('"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -property installationPath -latest -prerelease -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64') DO @(set VCVARSALL="%%i\VC\Auxiliary\Build\vcvarsall.bat")
)
if ^%VCVARSALL:~0,1% NEQ ^" SET VCVARSALL="%VCVARSALL%"
call %VCVARSALL% x86_arm64
pushd %LIBFFI_SOURCE%
%SH% --login -lc "cygcheck -dc cygwin"
set GET_MSVCC=%SH% -lc "cd $LIBFFI_SOURCE; export MSVCC=`/usr/bin/find $PWD -name msvcc.sh`; echo ${MSVCC};"
FOR /F "usebackq delims==" %%i IN (`%GET_MSVCC%`) do @set MSVCC=%%i
set MSVCC=%MSVCC% -marm64

echo Configuring and building libffi for ARM64
 
%SH% -lc "(cd $LIBFFI_SOURCE; ./autogen.sh)"
%SH% -lc "(cd $LIBFFI_SOURCE; ./configure CC='%MSVCC%' CXX='%MSVCC%' LD='link' CPP='cl -nologo -EP' CXXCPP='cl -nologo -EP' CPPFLAGS='-DFFI_BUILDING_DLL'  NM='dumpbin -symbols' STRIP=':' --build=$BUILD --host=$HOST --enable-static --disable-shared)"
%SH% -lc "(cd $LIBFFI_SOURCE; cp src/aarch64/ffitarget.h include)"
%SH% -lc "(cd $LIBFFI_SOURCE; make)"

set LIBFFI_OUT=%~dp0

echo copying files to %LIBFFI_OUT%
if not exist %LIBFFI_OUT%\include (md %LIBFFI_OUT%\include)
copy %LIBFFI_SOURCE%\%HOST%\.libs\libffi.lib %LIBFFI_OUT%\ffi.lib || exit /B 1
copy %LIBFFI_SOURCE%\%HOST%\fficonfig.h %LIBFFI_OUT%\include || exit /B 1
copy %LIBFFI_SOURCE%\%HOST%\include\*.h %LIBFFI_OUT%\include || exit /B 1
popd
exit /B
 
:InstallCygwin
setlocal
set CYG_ROOT=C:/cygwin
set CYG_CACHE=C:/cygwin/var/cache/setup
set CYG_MIRROR=http://mirrors.kernel.org/sourceware/cygwin/
powershell -c "Invoke-WebRequest https://cygwin.com/setup-x86.exe -OutFile setup.exe"
setup.exe -qgnNdO -R "%CYG_ROOT%" -s "%CYG_MIRROR%" -l "%CYG_CACHE%" -P dejagnu -P autoconf -P automake -P libtool -P make
endlocal
exit /B
