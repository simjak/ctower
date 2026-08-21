import type { ReactElement } from "react";
import { Button, PageHead } from "../ui/primitives";
import { DefinitionForm } from "./compose/DefinitionForm";
import { modeTitle, PURPOSE } from "./mode";
import { ReviewPanel } from "./review/ReviewPanel";
import { StandingLine } from "./StandingLine";
import { useCompany } from "./useCompany";
import type { Seed } from "./useSeed";

/**
 * The Company page. One page.
 *
 * There is no stepper, because there is nothing to step through until the
 * operator changes something. The definition and what the registry says about
 * it are the page; review and apply are what edits produce, and they exist for
 * exactly as long as the edits do.
 */
export function CompanyPage({ seed }: { readonly seed: Seed }): ReactElement {
  const company = useCompany(seed);
  const digest = seed.kind === "exported" ? seed.result.bundle_digest : null;

  if (company.mode === "review") {
    return (
      <ReviewPanel
        review={company.review}
        applied={company.applied}
        armed={company.armed}
        onArm={company.setArmed}
        onApply={company.apply}
        onBack={company.closeReview}
      />
    );
  }

  return (
    <>
      <PageHead
        title={modeTitle({ kind: "answered", value: seed })}
        subtitle={
          <>
            <span>{PURPOSE}</span>
          </>
        }
      >
        <StandingLine standing={company.standing} edits={company.edits} digest={digest} />
      </PageHead>

      <DefinitionForm draft={company.draft} onDraft={company.setDraft} />

      {company.edits === 0 ? null : (
        <footer className="mt-6 flex items-center gap-2 border-t border-line pt-4">
          <span className="flex-1" />
          <Button variant="primary" onClick={company.openReview}>
            Review changes ({company.edits}) →
          </Button>
        </footer>
      )}
    </>
  );
}
