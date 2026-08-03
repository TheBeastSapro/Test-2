' Forgecast — double-click this one.
'
' Why a .vbs and not the .bat
' ---------------------------
' A .bat cannot start without a console. Windows creates one for cmd.exe before the
' first line runs, so the black window is not something the batch file opens — it is
' the batch file. Hiding it from inside is not possible; it has to never be created.
'
' Windows Script Host can start a process with the window hidden, and it is present on
' every Windows install, so it needs nothing downloaded to work. That is the whole
' reason this file exists.
'
' The failure case is the interesting one. A hidden window that fails is a
' double-click that does nothing at all, which is worse than a black box: there is no
' error to read and nothing to report. So on a non-zero exit this re-runs the same
' command *visibly* and leaves it open, which puts the operator in front of the real
' message. `Forgecast.bat` is still there for anyone who wants the console every time.

Option Explicit

Dim shell, fso, here, quiet, status, python

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' The folder this script sits in, not the working directory — a shortcut, a pinned
' taskbar item and a double-click from Explorer each start with a different cwd.
here = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = here

' Tells the launcher not to wait for a keypress. A `pause` in a window nobody can see
' is a process that hangs forever with no way to notice.
shell.Environment("PROCESS")("FORGECAST_NO_PAUSE") = "1"

' pythonw.exe over python.exe: same interpreter, no console. Preferred for the same
' reason this file exists at all. `py -3` is the launcher shim Python's installer adds
' and it is the most reliable way to find an interpreter that is not on PATH.
If fso.FileExists(here & "\.venv\Scripts\pythonw.exe") Then
  python = """" & here & "\.venv\Scripts\pythonw.exe"""
ElseIf ExistsOnPath(shell, "pythonw.exe") Then
  python = "pythonw.exe"
ElseIf ExistsOnPath(shell, "py.exe") Then
  python = "py -3w"
Else
  MsgBox "Python was not found on this machine." & vbCrLf & vbCrLf & _
         "Install Python 3.11 or newer from https://python.org/downloads" & vbCrLf & _
         "and tick ""Add python.exe to PATH"" during setup.", _
         vbExclamation, "Forgecast"
  WScript.Quit 1
End If

' 0 = hidden, True = wait for it. Waiting is what makes the exit code available, which
' is what makes the visible retry below possible.
status = shell.Run(python & " """ & here & "\launcher.py""", 0, True)

If status <> 0 Then
  ' Second attempt, visible and paused, so the reason is on screen. Run through cmd
  ' with python.exe rather than pythonw.exe — a console interpreter is the point here.
  shell.Environment("PROCESS")("FORGECAST_NO_PAUSE") = ""
  shell.Run "cmd /k """ & here & "\Forgecast.bat""", 1, False
End If

Function ExistsOnPath(sh, exeName)
  ' `where` is the only reliable answer: PATH is per-process, and testing well-known
  ' install folders misses a Microsoft Store Python and every custom location.
  ExistsOnPath = (sh.Run("cmd /c where " & exeName & " >nul 2>nul", 0, True) = 0)
End Function
