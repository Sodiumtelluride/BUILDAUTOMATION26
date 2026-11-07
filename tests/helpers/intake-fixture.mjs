import { CONTENT_OPTIONS, DOMAIN_OPTIONS, LOGO_OPTIONS } from "../../src/lib/intake/contract.ts";

export function intakeAnswers(overrides = {}) {
  return {
    sensitiveDataAcknowledged: true,
    organizationName: "Pioneer Community",
    primaryContactName: "Maria Santos",
    primaryContactEmail: "maria@example.org",
    organizationType: "Nonprofit",
    primaryGoal: "Share information or resources",
    organizationDescription: "We connect local families with community resources and organize volunteers to support our neighbors.",
    targetAudience: "Families and volunteers throughout Western Massachusetts.",
    pages: ["Home", "About", "Contact"],
    features: ["Contact form"],
    featureDetails: "",
    hasLogo: LOGO_OPTIONS[2],
    brandColors: "#2e7d32",
    brandFonts: "Inter",
    visualStyle: "A warm, welcoming design with clear typography and community photography.",
    referenceWebsites: ["example.org", "", ""],
    hasContent: CONTENT_OPTIONS[2],
    existingContent: "",
    toneAndVoice: ["Friendly"],
    contentRestrictions: "",
    hasDomain: DOMAIN_OPTIONS[2],
    domainName: "",
    integrations: [],
    integrationDetails: "",
    additionalInfo: "",
    ...overrides,
  };
}
