# Microsoft Visual C++ app-local runtime

The private Python runtime ZIP contains these unmodified x64 Microsoft runtime
binaries beside `python.exe`: `msvcp140.dll`, `msvcp140_1.dll`,
`vcruntime140.dll`, and `vcruntime140_1.dll`. Python and native wheels use these DLLs.
They are separate proprietary components, not part of this project's MIT license.

Version: **14.51.36247.0**, obtained on 2026-10-15 from Microsoft's official
Visual C++ v14 redistributable. `runtime/vc-runtime.json` records the immutable
download URL, archive SHA256, cabinet locations and individual file SHA256 values.
`scripts/fetch-vc-runtime.ps1` extracts the DLLs as data. The official license page
linked by that redistributable is retained as `MICROSOFT-VC-RUNTIME-LICENSE.html`,
with its source URL and exact hash in the manifest. It never runs an installer.

Microsoft documents app-local deployment here:

- [Deployment in Microsoft C++](https://learn.microsoft.com/en-us/cpp/windows/deployment-in-visual-cpp?view=msvc-170)
- [Redistribute Visual C++ files](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)
- [Visual Studio 2022 distributable code list](https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution)

Redistribution of these files is restricted to qualifying licensed Visual Studio
users and subject to the applicable Visual Studio license terms. The publisher
must establish its own entitlement before distributing a package. The included
runtime end-user license is not a substitute for a publisher's redistribution
rights. Preparing and testing this local package does not establish those rights.
Keep Microsoft's copyright and license notices intact and do not modify the DLLs.

The plugin author must track runtime security fixes and release updated packages;
Windows Update does not service the plugin's app-local copies. Normal Windows
system libraries, including Universal CRT and DirectX system components on the
supported Windows releases, are supplied by Windows and are not redistributed here.
