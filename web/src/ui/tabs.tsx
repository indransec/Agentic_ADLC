// Accessible tabs: a tablist of buttons (arrow keys move between them) and one panel.
import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export interface Tab {
  label: string;
  render: () => ReactNode;
}

export function Tabs({ tabs, label }: { tabs: readonly Tab[]; label: string }) {
  const [selected, setSelected] = useState(0);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const id = useId();

  function onKey(event: KeyboardEvent) {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (step === 0) return;
    const next = (selected + step + tabs.length) % tabs.length;
    setSelected(next);
    buttons.current[next]?.focus();
  }

  const current = tabs[selected];
  return (
    <div className="tabs">
      <div role="tablist" aria-label={label}>
        {tabs.map((tab, index) => (
          <button
            key={tab.label}
            ref={(el) => {
              buttons.current[index] = el;
            }}
            type="button"
            role="tab"
            id={`${id}-tab-${String(index)}`}
            aria-selected={index === selected}
            aria-controls={`${id}-panel`}
            tabIndex={index === selected ? 0 : -1}
            onClick={() => {
              setSelected(index);
            }}
            onKeyDown={onKey}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-tab-${String(selected)}`}>
        {current?.render()}
      </div>
    </div>
  );
}
