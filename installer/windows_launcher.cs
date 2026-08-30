using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class AbaqusCodexAssistantLauncher
{
    [STAThread]
    private static int Main()
    {
        string applicationRoot = AppDomain.CurrentDomain.BaseDirectory;
        string privatePython = Path.Combine(
            applicationRoot,
            "runtime",
            "pythonw.exe"
        );
        if (!File.Exists(privatePython))
        {
            MessageBox.Show(
                "The private application runtime is missing. Reinstall Abaqus Codex Assistant.",
                "Abaqus Codex Assistant",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }

        try
        {
            ProcessStartInfo start = new ProcessStartInfo();
            start.FileName = privatePython;
            start.Arguments = "-I -m abaqus_codex assistant";
            start.WorkingDirectory = applicationRoot;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            Process.Start(start);
            return 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "Abaqus Codex Assistant could not start. Reinstall the application.\n\n" +
                error.Message,
                "Abaqus Codex Assistant",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }
    }
}
