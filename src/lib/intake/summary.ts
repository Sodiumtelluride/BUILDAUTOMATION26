// One definition of how intake answers are grouped and labelled.
// Used by the review step in the form and by the confirmation email, so the
// copy a submitter receives always matches what they reviewed before submitting.

import { CONTENT_PARTIAL, CONTENT_YES, DOMAIN_OWNED, LOGO_UPLOAD, type IntakeAnswers } from "./contract";

export const SECTION_TITLES = [
  "Organization & Contact",
  "Project Goals",
  "Design & Branding",
  "Content",
  "Technical Details",
  "Review & Submit",
] as const;

export interface IntakeSummaryFiles {
  logo: string | null;
  content: string[];
}

export interface IntakeSummaryGroup {
  /** Index of the form section these answers came from (0–5). */
  section: number;
  title: string;
  rows: [label: string, value: string][];
}

const list = (values: string[]) => values.filter((value) => value.trim()).join(", ");

/** Groups answers by form section. Rows with empty values are removed. */
export function summarizeIntake(answers: IntakeAnswers, files: IntakeSummaryFiles): IntakeSummaryGroup[] {
  const hasContent = answers.hasContent === CONTENT_YES || answers.hasContent === CONTENT_PARTIAL;
  const groups: IntakeSummaryGroup[] = [
    { section: 0, title: SECTION_TITLES[0], rows: [
      ["Organization", answers.organizationName],
      ["Contact", `${answers.primaryContactName} · ${answers.primaryContactEmail}`],
      ["Type", answers.organizationType],
    ] },
    { section: 1, title: SECTION_TITLES[1], rows: [
      ["Goal", answers.primaryGoal],
      ["About", answers.organizationDescription],
      ["Audience", answers.targetAudience],
      ["Pages", list(answers.pages)],
      ["Features", list(answers.features)],
      ["Feature details", answers.featureDetails],
    ] },
    { section: 2, title: SECTION_TITLES[2], rows: [
      ["Logo", answers.hasLogo === LOGO_UPLOAD ? files.logo ?? "" : answers.hasLogo],
      ["Colors", answers.brandColors],
      ["Fonts", answers.brandFonts],
      ["Style", answers.visualStyle],
      ["References", list(answers.referenceWebsites)],
    ] },
    { section: 3, title: SECTION_TITLES[3], rows: [
      ["Content", answers.hasContent],
      ...(hasContent
        ? [["Existing text", answers.existingContent], ["Documents", list(files.content)]] as [string, string][]
        : []),
      ["Tone", list(answers.toneAndVoice)],
      ["Avoid", answers.contentRestrictions],
    ] },
    { section: 4, title: SECTION_TITLES[4], rows: [
      ["Domain", answers.hasDomain === DOMAIN_OWNED ? answers.domainName : answers.hasDomain],
      ["Integrations", list(answers.integrations)],
      ["Integration details", answers.integrationDetails],
    ] },
    { section: 5, title: "Additional details", rows: [
      ["Additional details", answers.additionalInfo],
    ] },
  ];
  return groups
    .map((group) => ({ ...group, rows: group.rows.filter(([, value]) => value.trim()) }))
    .filter((group) => group.rows.length > 0);
}
