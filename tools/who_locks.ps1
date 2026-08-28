param([string]$Path)
$src = @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class RM {
    [StructLayout(LayoutKind.Sequential)]
    struct RM_UNIQUE_PROCESS { public int dwProcessId; public System.Runtime.InteropServices.ComTypes.FILETIME ProcessStartTime; }
    enum RM_APP_TYPE { Unknown=0, MainWindow=1, OtherWindow=2, Service=3, Explorer=4, Console=5, Critical=1000 }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    struct RM_PROCESS_INFO {
        public RM_UNIQUE_PROCESS Process;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=256)] public string strAppName;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst=64)] public string strServiceShortName;
        public RM_APP_TYPE ApplicationType;
        public uint AppStatus;
        public uint TSSessionId;
        [MarshalAs(UnmanagedType.Bool)] public bool bRestartable;
    }
    [DllImport("rstrtmgr.dll", CharSet=CharSet.Unicode)] static extern int RmStartSession(out uint pSessionHandle, int dwSessionFlags, string strSessionKey);
    [DllImport("rstrtmgr.dll")] static extern int RmEndSession(uint pSessionHandle);
    [DllImport("rstrtmgr.dll", CharSet=CharSet.Unicode)] static extern int RmRegisterResources(uint pSessionHandle, uint nFiles, string[] rgsFilenames, uint nApplications, [In] RM_UNIQUE_PROCESS[] rgApplications, uint nServices, string[] rgsServiceNames);
    [DllImport("rstrtmgr.dll")] static extern int RmGetList(uint dwSessionHandle, out uint pnProcInfoNeeded, ref uint pnProcInfo, [In, Out] RM_PROCESS_INFO[] rgAffectedApps, ref uint lpdwRebootReasons);
    public static List<string> Who(string path) {
        var key = Guid.NewGuid().ToString();
        uint h; var rc = RmStartSession(out h, 0, key);
        var result = new List<string>();
        if (rc != 0) { result.Add("RmStartSession=" + rc); return result; }
        try {
            string[] resources = new[] { path };
            rc = RmRegisterResources(h, (uint)resources.Length, resources, 0, null, 0, null);
            if (rc != 0) { result.Add("RmRegisterResources=" + rc); return result; }
            uint pnProcInfo = 0, pnProcInfoNeeded = 0, lpdwRebootReasons = 0;
            rc = RmGetList(h, out pnProcInfoNeeded, ref pnProcInfo, null, ref lpdwRebootReasons);
            if (rc == 234) {
                var info = new RM_PROCESS_INFO[pnProcInfoNeeded];
                pnProcInfo = pnProcInfoNeeded;
                rc = RmGetList(h, out pnProcInfoNeeded, ref pnProcInfo, info, ref lpdwRebootReasons);
                if (rc == 0) for (int i = 0; i < pnProcInfo; i++) result.Add(info[i].Process.dwProcessId + "\t" + info[i].strAppName + "\t" + info[i].ApplicationType.ToString());
                else result.Add("RmGetList(2)=" + rc);
            } else if (rc != 0) { result.Add("RmGetList=" + rc); }
            else { result.Add("(nothing)"); }
        } finally { RmEndSession(h); }
        return result;
    }
}
"@
Add-Type -TypeDefinition $src -Language CSharp
[RM]::Who($Path) | ForEach-Object { Write-Output $_ }
