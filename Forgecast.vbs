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
' error to read and nothing to report.
'
' The first answer to that was to re-run the same command *visibly* on a non-zero exit.
' It worked and it was wrong: a crash then produced exactly the black console this file
' exists to prevent, and two of them, because the visible re-run starts a child of its
' own. The complaint was about the box, not about the error inside it.
'
' So every run is logged, and a failure opens a dialog naming what went wrong with the
' log one click away. A message box is not a console: it says one thing, it is
' dismissed, and it leaves nothing in the taskbar. `Forgecast.bat` is still there for
' anyone who wants the console every time.

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

Dim logPath, command
logPath = here & "\forgecast-launch.log"

' Through cmd so the output can be redirected to a file, and hidden so cmd's own window
' is never drawn. /s makes cmd take everything between the outer quotes verbatim, which
' is what allows two quoted paths and a quoted redirect target on one line.
'
' 0 = hidden, True = wait for it. Waiting is what makes the exit code available, which
' is what makes the dialog below possible at all.
command = "cmd /s /c """ & python & " """ & here & "\launcher.py"" > """ & logPath & """ 2>&1"""
status = shell.Run(command, 0, True)

If status <> 0 Then
  ShowFailure logPath, status
End If

Sub ShowFailure(path, code)
  ' The last few lines, not the whole log: a traceback's useful sentence is at the
  ' bottom, and a message box holding four hundred lines is one nobody reads.
  Dim body, text, parts, index, first
  body = ""
  If fso.FileExists(path) Then
    On Error Resume Next
    text = fso.OpenTextFile(path, 1).ReadAll()
    On Error GoTo 0
    parts = Split(Replace(text, vbCrLf, vbLf), vbLf)
    first = UBound(parts) - 12
    If first < 0 Then first = 0
    For index = first To UBound(parts)
      If Trim(parts(index)) <> "" Then body = body & parts(index) & vbCrLf
    Next
  End If
  If Trim(body) = "" Then body = "It stopped with code " & code & " and wrote nothing."

  If MsgBox("Forgecast could not start." & vbCrLf & vbCrLf & body & vbCrLf & _
            "The full log is at:" & vbCrLf & path & vbCrLf & vbCrLf & _
            "Open it now?", vbExclamation + vbYesNo, "Forgecast") = vbYes Then
    ' Notepad, not a console. It is on every Windows install, and it closes like a
    ' document rather than sitting in the taskbar as a terminal.
    shell.Run "notepad.exe """ & path & """", 1, False
  End If
End Sub

Function ExistsOnPath(sh, exeName)
  ' `where` is the only reliable answer: PATH is per-process, and testing well-known
  ' install folders misses a Microsoft Store Python and every custom location.
  ExistsOnPath = (sh.Run("cmd /c where " & exeName & " >nul 2>nul", 0, True) = 0)
End Function
