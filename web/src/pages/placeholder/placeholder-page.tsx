// A page not rebuilt yet (feature 022 builds them story by story). Until the cutover, the
// previous application serves it.
import { PageHeader } from "../../ui/page-header";

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <>
      <PageHeader title={title} />
      <p className="caption">
        This page is not in the new application yet. Use the previous application meanwhile.
      </p>
    </>
  );
}
