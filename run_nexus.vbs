Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "G:\Personal\Nexus-River-View"
WshShell.Run "python app.py", 0, False