import { closeMainWindow, showToast, Toast } from "@vicinae/api";
import { run } from "./backend";
export default async function Stop() {
  try { await run("stop"); await closeMainWindow(); }
  catch (e) { await showToast({ style: Toast.Style.Failure, title: "Could not stop recording", message: String(e) }); }
}
