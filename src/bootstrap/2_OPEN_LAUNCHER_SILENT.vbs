Option Explicit
Dim sh, fs, base, command
Set sh = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
base = fs.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = base
' Stable boot entry point; future launcher upgrades do not replace it.
command = "cmd.exe /d /c py -3.12 """ & base & "\launch_host.pyw"""
sh.Run command, 0, False
