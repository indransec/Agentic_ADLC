export function RawHtml({ text }: { text: string }) {
  return <div dangerouslySetInnerHTML={{ __html: text }} />;
}
