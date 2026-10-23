Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\Mark-LVI"
WshShell.Environment("PROCESS")("PYTHONUTF8") = "1"
WshShell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
WshShell.Run "D:\Mark-LVI\.venv\Scripts\pythonw.exe D:\Mark-LVI\main.py", 0, False
