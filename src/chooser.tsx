import { Action, ActionPanel, Grid, Icon } from "@vicinae/api";
import Capture from "./capture";

export default function Chooser() {
  return <Grid navigationTitle="Screen Capture" columns={2} aspectRatio="16/9"
    inset={Grid.Inset.Large} filtering={false}
    searchBarPlaceholder="Choose Screenshot or Screencast · arrows to select, Enter to open">
    <Grid.Item id="screenshot" title="Screenshot" subtitle="Capture an area, window, or monitor"
      content={Icon.Camera} actions={<ActionPanel>
        <Action.Push title="Take a Screenshot" target={<Capture mode="screenshot"/>}/>
      </ActionPanel>}/>
    <Grid.Item id="screencast" title="Screencast" subtitle="Record a GIF or video · stop a recording"
      content={Icon.Video} actions={<ActionPanel>
        <Action.Push title="Open Screencast" target={<Capture mode="record"/>}/>
      </ActionPanel>}/>
  </Grid>;
}
