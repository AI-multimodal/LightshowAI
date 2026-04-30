// Inline iframe for embedding XANES plots and crystal-structure viewers
// inside the Chainlit chat. `props.src` is served by lightshowai-plots.service.

export default function Iframe() {
  const currentProps = typeof props === "undefined" ? {} : props;
  const src = typeof currentProps.src === "string" ? currentProps.src : "";
  const height = Number(currentProps.height) || 520;
  const title = currentProps.title || "HTML preview";

  if (!src) {
    return (
      <div className="mt-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
        HTML source is unavailable.
      </div>
    );
  }

  return (
    <div style={{ width: "100%", marginTop: 8 }}>
      <iframe
        src={src}
        title={title}
        style={{
          width: "100%",
          height: `${height}px`,
          border: "1px solid #2a2a2a",
          borderRadius: 8,
          background: "#fff"
        }}
        sandbox="allow-scripts allow-same-origin allow-popups allow-downloads"
        loading="lazy"
        referrerPolicy="no-referrer"
      />
    </div>
  );
}
