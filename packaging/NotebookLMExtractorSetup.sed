[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=<None>
AdminQuietInstCmd=%AppLaunched%
UserQuietInstCmd=%AppLaunched%
SourceFiles=SourceFiles

[SourceFiles]
SourceFiles0=C:\Users\A\Desktop\Newolder_2\NoteBookLM\installer_payload\

[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=

[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=NotebookLM Extractor was installed successfully.
TargetName=C:\Users\A\Desktop\Newolder_2\NoteBookLM\release\NotebookLMExtractor_Setup.exe
FriendlyName=NotebookLM Extractor Setup
AppLaunched=cmd.exe /c install.cmd
FILE0="NotebookLMExtractor.zip"
FILE1="install.cmd"
FILE2="install.ps1"
