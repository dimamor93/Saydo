Option Explicit

Dim shell, fso, projectDir, pythonw, mainPy

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = projectDir & "\.venv\Scripts\pythonw.exe"
mainPy = projectDir & "\main.py"

If Not fso.FileExists(pythonw) Then
    MsgBox "Saydo: Python environment not found:" & vbCrLf & pythonw, 16, "Saydo"
    WScript.Quit 1
End If

If Not fso.FileExists(mainPy) Then
    MsgBox "Saydo: main.py not found:" & vbCrLf & mainPy, 16, "Saydo"
    WScript.Quit 1
End If

shell.CurrentDirectory = projectDir
shell.Run """" & pythonw & """ """ & mainPy & """", 0, False

Set fso = Nothing
Set shell = Nothing
