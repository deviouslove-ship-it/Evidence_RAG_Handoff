import { ChatAgentDock } from "./ChatAgentDock";

export function DesktopOrb() {
  return (
    <div className="orb-stage">
      <ChatAgentDock standaloneDesktop />
    </div>
  );
}
