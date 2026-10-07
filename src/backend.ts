import { environment } from "@vicinae/api";
import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";
import { join } from "node:path";
const helper = join(environment.assetsPath, "capture.py");
export const run = async (...args: string[]) => (await promisify(execFile)("/usr/bin/python3", [helper, ...args])).stdout;
export async function launch(args: string[]) {
  // A detached supervisor survives closing the extension view.
  const child = spawn("/usr/bin/python3", [helper, ...args], { detached: true, stdio: "ignore" });
  await new Promise<void>((resolve, reject) => { child.once("spawn", resolve); child.once("error", reject); });
  child.unref();
}
