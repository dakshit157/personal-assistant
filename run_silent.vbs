Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir
WshShell.Environment("PROCESS")("PYTHONUTF8") = "1"
WshShell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
pythonwExe = currentDir & "\.venv\Scripts\pythonw.exe"
mainScript = currentDir & "\main.py"
WshShell.Run """" & pythonwExe & """ """ & mainScript & """", 0, False
