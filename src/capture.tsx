import { Action, ActionPanel, Form, closeMainWindow } from "@vicinae/api";
import { useEffect, useState } from "react";
import { launch, run } from "./backend";

export default function Capture({ mode }: { mode: "screenshot" | "record" }) {
  const [target, setTarget] = useState("area");
  const [audio, setAudio] = useState("none");
  const [format, setFormat] = useState("gif");
  const [destination, setDestination] = useState("copy");
  const [delay, setDelay] = useState("0");
  const [status, setStatus] = useState<{phase?: string; elapsed?: number}>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    const refresh = () => run("status").then(s => { if (alive) setStatus(JSON.parse(s)); }).catch(() => {});
    refresh(); const timer = setInterval(refresh, 1000);
    return () => { alive = false; clearInterval(timer); };
  }, []);
  const active = mode === "record" && Boolean(status.phase);
  async function submit() {
    if (busy) return;
    setBusy(true); setError("");
    try {
      if (active) { await run("stop"); }
      else {
        await run("check", "--mode", mode, "--target", target, "--destination", destination, "--audio", format === "gif" ? "none" : audio);
        await closeMainWindow();
        await launch([mode, "--target", target, "--audio", format === "gif" ? "none" : audio, "--destination", destination, "--delay", delay, ...(format === "gif" ? ["--gif-only"] : format === "both" ? ["--gif"] : [])]);
      }
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  return <Form navigationTitle={mode === "screenshot" ? "Screenshot" : "Record Video"} isLoading={busy} actions={<ActionPanel>
    <Action.SubmitForm title={active ? "Stop and Save Recording" : mode === "screenshot" ? "Take Screenshot" : "Start Recording"} onSubmit={submit}/>
  </ActionPanel>}>
    {active ? <Form.Description title="Recording" text={`${status.phase} · ${status.elapsed ?? 0}s\nPress Enter to stop and save, or use Stop Screen Recording in Vicinae.`}/> : <>
      <Form.Dropdown id="target" title="What to capture" value={target} onChange={setTarget}>
        <Form.Dropdown.Item value="area" title="Select an Area"/><Form.Dropdown.Item value="window" title="Choose a Window"/>
        <Form.Dropdown.Item value="active" title="Active Window"/><Form.Dropdown.Item value="output" title="Current Monitor"/>
        {mode === "screenshot" && <Form.Dropdown.Item value="screen" title="All Monitors"/>}
      </Form.Dropdown>
      {mode === "screenshot" ? <Form.Dropdown id="destination" title="Destination" value={destination} onChange={setDestination}>
        <Form.Dropdown.Item value="savecopy" title="Save and Copy to Clipboard"/><Form.Dropdown.Item value="copy" title="Clipboard Only"/><Form.Dropdown.Item value="save" title="Save Only"/>
      </Form.Dropdown> : <>
        <Form.Dropdown id="format" title="Format" value={format} onChange={setFormat}>
          <Form.Dropdown.Item value="gif" title="GIF Only (Silent)"/><Form.Dropdown.Item value="mp4" title="MP4 Video"/><Form.Dropdown.Item value="both" title="MP4 and GIF"/>
        </Form.Dropdown>
        {format !== "gif" && <Form.Dropdown id="audio" title="Audio" value={audio} onChange={setAudio}>
          <Form.Dropdown.Item value="none" title="No Audio"/><Form.Dropdown.Item value="system" title="System Audio"/><Form.Dropdown.Item value="microphone" title="Microphone"/>
        </Form.Dropdown>}
        <Form.Description title="Stop recording" text="Open Record Video again and press Enter, or use Stop Screen Recording. On Sway, Super+Print (or Ctrl+Shift+Print) stops recording from any window. Window recordings capture a fixed rectangle; keep the window in place."/>
      </>}
      <Form.Dropdown id="delay" title="Delay after selection" value={delay} onChange={setDelay}>
        <Form.Dropdown.Item value="0" title="None"/><Form.Dropdown.Item value="3" title="3 Seconds"/><Form.Dropdown.Item value="5" title="5 Seconds"/><Form.Dropdown.Item value="10" title="10 Seconds"/>
      </Form.Dropdown>
      <Form.Description title="Saved files" text={mode === "screenshot" ? "Pictures/Screenshots · PNG" : `Videos/Screencasts · ${format === "gif" ? "GIF only" : format === "mp4" ? "MP4" : "MP4 and GIF"}`}/>
    </>}
    {error && <Form.Description title="Error" text={error}/>}
  </Form>;
}
