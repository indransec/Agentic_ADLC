// The page title (platform words) and what the page is for. Focus moves to it when the page
// opens, so keyboard and screen-reader users start at the top (FR-028).
import { useEffect, useRef } from "react";

export function PageHeader({ title, caption }: { title: string; caption?: string }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [title]);
  return (
    <header className="page-header">
      <h1 ref={heading} tabIndex={-1}>
        {title}
      </h1>
      {caption !== undefined && <p className="caption">{caption}</p>}
    </header>
  );
}
