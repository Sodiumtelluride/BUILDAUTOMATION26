"use client";
import { useState, useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, Upload, X, Check } from "lucide-react";

type FormData = {
  organizationName: string;
  primaryContactName: string;
  primaryContactEmail: string;
  organizationType: string;
  primaryGoal: string;
  organizationDescription: string;
  targetAudience: string;
  pages: string[];
  additionalFeatureDetails: string;
  hasLogo: string;
  brandColors: string;
  brandFonts: string;
  visualStyle: string;
  referenceWebsites: string[];
  logoFile: File | null;
  hasContent: string;
  existingContent: string;
  contentFiles: File[];
  toneAndVoice: string[];
  contentRestrictions: string;
  hasDomain: string;
  domainName: string;
  integrations: string[];
  integrationDetails: string;
  additionalInfo: string;
};

const SECTION_TITLES = [
  "Organization & Contact",
  "Project Goals",
  "Design & Branding",
  "Content",
  "Technical Details",
  "Additional Information",
];

const initialFormData: FormData = {
  organizationName: "",
  primaryContactName: "",
  primaryContactEmail: "",
  organizationType: "",
  primaryGoal: "",
  organizationDescription: "",
  targetAudience: "",
  pages: [],
  additionalFeatureDetails: "",
  hasLogo: "",
  brandColors: "",
  brandFonts: "",
  visualStyle: "",
  referenceWebsites: ["", "", ""],
  logoFile: null,
  hasContent: "",
  existingContent: "",
  contentFiles: [],
  toneAndVoice: [],
  contentRestrictions: "",
  hasDomain: "",
  domainName: "",
  integrations: [],
  integrationDetails: "",
  additionalInfo: "",
};

// Shared field components

function FieldInput({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <div className="mb-5">
      <label className="block text-white text-sm font-medium mb-2 leading-snug">
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-white text-gray-900 rounded-xl px-4 py-3 text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#DC4436]"
      />
    </div>
  );
}

function FieldTextarea({
  label,
  value,
  onChange,
  placeholder,
  rows = 4,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  maxLength?: number;
}) {
  return (
    <div className="mb-5">
      <label className="block text-white text-sm font-medium mb-2 leading-snug">
        {label}
      </label>
      <textarea
        value={value}
        onChange={(e) =>
          onChange(maxLength ? e.target.value.slice(0, maxLength) : e.target.value)
        }
        placeholder={placeholder}
        rows={rows}
        className="w-full bg-white text-gray-900 rounded-xl px-4 py-3 text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#DC4436] resize-none"
      />
      {maxLength && (
        <p className="text-right text-xs text-gray-500 mt-1">
          {value.length}/{maxLength}
        </p>
      )}
    </div>
  );
}

function FieldSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <div className="mb-5">
      <label className="block text-white text-sm font-medium mb-2 leading-snug">
        {label}
      </label>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full bg-white text-gray-900 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#DC4436] appearance-none cursor-pointer pr-10"
        >
          <option value="">Select</option>
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
        <ChevronRight
          size={16}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 rotate-90 pointer-events-none"
        />
      </div>
    </div>
  );
}

function FieldMultiSelect({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (v: string[]) => void;
}) {
  const toggle = (opt: string) => {
    if (selected.includes(opt)) {
      onChange(selected.filter((s) => s !== opt));
    } else {
      onChange([...selected, opt]);
    }
  };
  return (
    <div className="mb-5">
      <label className="block text-white text-sm font-medium mb-3 leading-snug">
        {label}
      </label>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={`px-4 py-2 rounded-full border text-sm font-medium transition-colors ${
              selected.includes(opt)
                ? "bg-white text-black border-white"
                : "bg-transparent text-white border-white/70 hover:border-white hover:bg-white/10"
            }`}
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  );
}

function FieldFileUpload({
  label,
  accept,
  acceptLabel,
  onFile,
  fileName,
}: {
  label: string;
  accept: string;
  acceptLabel: string;
  onFile: (f: File) => void;
  fileName?: string;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <div className="mb-5">
      <label className="block text-white text-sm font-medium mb-2 leading-snug">
        {label}
      </label>
      <div
        onClick={() => fileRef.current?.click()}
        className="border-2 border-dashed border-gray-600 rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer hover:border-[#DC4436] transition-colors bg-[#2a2a2a]"
      >
        <div className="mb-2 text-gray-400">
          <Upload size={28} />
        </div>
        {fileName ? (
          <p className="text-white text-sm text-center">{fileName}</p>
        ) : (
          <p className="text-gray-500 text-xs text-center">{acceptLabel}</p>
        )}
        <input
          ref={fileRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
        />
      </div>
    </div>
  );
}

// Section components

function Section1({
  data,
  set,
}: {
  data: FormData;
  set: (k: keyof FormData, v: FormData[keyof FormData]) => void;
}) {
  return (
    <>
      <FieldInput
        label="Organization Name"
        value={data.organizationName}
        onChange={(v) => set("organizationName", v)}
        placeholder="e.g., BUILD UMASS"
      />
      <FieldInput
        label="Primary Contact Name"
        value={data.primaryContactName}
        onChange={(v) => set("primaryContactName", v)}
        placeholder="e.g., John Smith"
      />
      <FieldInput
        label="Primary Contact Email"
        value={data.primaryContactEmail}
        onChange={(v) => set("primaryContactEmail", v)}
        placeholder="e.g., johnsmith@email.com"
        type="email"
      />
      <FieldSelect
        label="Organization Type"
        value={data.organizationType}
        onChange={(v) => set("organizationType", v)}
        options={["Nonprofit", "Student Club", "Startup", "Small Business", "Other"]}
      />
    </>
  );
}

function Section2({
  data,
  set,
}: {
  data: FormData;
  set: (k: keyof FormData, v: FormData[keyof FormData]) => void;
}) {
  return (
    <>
      <FieldSelect
        label="What is the primary goal of your website?"
        value={data.primaryGoal}
        onChange={(v) => set("primaryGoal", v)}
        options={[
          "Raise Awareness",
          "Generate Leads",
          "Sell Products",
          "Showcase Portfolio",
          "Provide Information",
          "Community Building",
          "Other",
        ]}
      />
      <FieldTextarea
        label="Describe your organization and what you do."
        value={data.organizationDescription}
        onChange={(v) => set("organizationDescription", v)}
        placeholder="BUILD UMass is a student-run organization that is committed to providing nonprofits, startups, and local businesses with scalable technology..."
        rows={4}
      />
      <FieldTextarea
        label="Who is your target audience?"
        value={data.targetAudience}
        onChange={(v) => set("targetAudience", v)}
        placeholder="BUILD UMass is a student-run organization that is committed to providing nonprofits, startups, and local businesses with scalable technology..."
        rows={4}
      />
      <FieldMultiSelect
        label="What pages do you need on your site?"
        options={[
          "Home",
          "Team",
          "About",
          "Services",
          "Events",
          "Blog",
          "Contact",
          "Gallery",
          "Donate",
          "Join/Apply",
          "FAQ",
          "Other",
        ]}
        selected={data.pages}
        onChange={(v) => set("pages", v)}
      />
      <FieldTextarea
        label="Are there any other features you need?"
        value={data.additionalFeatureDetails}
        onChange={(v) => set("additionalFeatureDetails", v)}
        placeholder="Contact form, Event calendar, Photo gallery, etc."
        rows={3}
      />
    </>
  );
}

function Section3({
  data,
  set,
}: {
  data: FormData;
  set: (k: keyof FormData, v: FormData[keyof FormData]) => void;
}) {
  return (
    <>
      <FieldSelect
        label="Do you have an existing logo?"
        value={data.hasLogo}
        onChange={(v) => set("hasLogo", v)}
        options={["Yes", "No", "In Progress"]}
      />
      <FieldTextarea
        label="Brand Colors"
        value={data.brandColors}
        onChange={(v) => set("brandColors", v)}
        placeholder="primary: #1E1E1E, secondary: white"
        rows={2}
      />
      <FieldTextarea
        label="Brand Fonts"
        value={data.brandFonts}
        onChange={(v) => set("brandFonts", v)}
        placeholder="primary: Sans, secondary: Arial"
        rows={2}
      />
      <FieldTextarea
        label="Describe the visual style you want"
        value={data.visualStyle}
        onChange={(v) => set("visualStyle", v)}
        placeholder="Clean and professional with a modern feel. We want it to look credible and established."
        rows={4}
      />
      <div className="mb-5">
        <label className="block text-white text-sm font-medium mb-3 leading-snug">
          Reference websites you like (1-3)
        </label>
        {data.referenceWebsites.map((url, i) => (
          <div key={i} className="flex items-center gap-2 mb-2">
            <input
              type="url"
              value={url}
              onChange={(e) => {
                const updated = [...data.referenceWebsites];
                updated[i] = e.target.value;
                set("referenceWebsites", updated);
              }}
              placeholder="http://example.com"
              className="flex-1 bg-white text-gray-900 rounded-xl px-4 py-3 text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#DC4436]"
            />
            <button
              type="button"
              onClick={() => {
                const updated = [...data.referenceWebsites];
                updated[i] = "";
                set("referenceWebsites", updated);
              }}
              className="text-gray-500 hover:text-white transition-colors flex-shrink-0"
            >
              <X size={18} />
            </button>
          </div>
        ))}
      </div>
      <FieldFileUpload
        label="Upload a logo"
        accept=".png,.jpg,.jpeg,.svg,.pdf"
        acceptLabel=".png, .jpg, .jpeg, .svg, .pdf"
        onFile={(f) => set("logoFile", f)}
        fileName={data.logoFile?.name}
      />
    </>
  );
}

function Section4({
  data,
  set,
}: {
  data: FormData;
  set: (k: keyof FormData, v: FormData[keyof FormData]) => void;
}) {
  return (
    <>
      <FieldSelect
        label="Do you have existing written content for your site?"
        value={data.hasContent}
        onChange={(v) => set("hasContent", v)}
        options={[
          "Yes, complete content",
          "Yes, partial content",
          "No, need help writing",
        ]}
      />
      <FieldTextarea
        label="Existing Text Content"
        value={data.existingContent}
        onChange={(v) => set("existingContent", v)}
        placeholder="5000 character limit"
        rows={4}
        maxLength={5000}
      />
      <FieldFileUpload
        label="Other Existing Content"
        accept=".pdf,.docx,.txt"
        acceptLabel=".pdf, .docx, .txt"
        onFile={(f) => set("contentFiles", [f])}
        fileName={data.contentFiles[0]?.name}
      />
      <FieldMultiSelect
        label="Tone and Voice"
        options={[
          "Professional",
          "Casual",
          "Friendly",
          "Inspiring",
          "Authoritative",
          "Playful",
          "Minimalist",
        ]}
        selected={data.toneAndVoice}
        onChange={(v) => set("toneAndVoice", v)}
      />
      <FieldTextarea
        label="Is there any content we should avoid?"
        value={data.contentRestrictions}
        onChange={(v) => set("contentRestrictions", v)}
        placeholder="Any topics or approaches to avoid..."
        rows={4}
      />
    </>
  );
}

function Section5({
  data,
  set,
}: {
  data: FormData;
  set: (k: keyof FormData, v: FormData[keyof FormData]) => void;
}) {
  return (
    <>
      <FieldSelect
        label="Do you have existing domain name?"
        value={data.hasDomain}
        onChange={(v) => set("hasDomain", v)}
        options={["Yes", "No", "Need Help Getting One"]}
      />
      <FieldInput
        label="Domain Name"
        value={data.domainName}
        onChange={(v) => set("domainName", v)}
        placeholder="buildumass.com"
      />
      <FieldMultiSelect
        label="What third-party tools do you need to connect to your site?"
        options={[
          "Google Analytics",
          "Mailchimp",
          "HubSpot",
          "Stripe",
          "Paypal",
          "Calendly",
          "Instagram Feed",
          "FaceBook Page",
        ]}
        selected={data.integrations}
        onChange={(v) => set("integrations", v)}
      />
      <FieldTextarea
        label="Integration Details"
        value={data.integrationDetails}
        onChange={(v) => set("integrationDetails", v)}
        placeholder="Account IDs, embed codes, integration notes..."
        rows={4}
      />
    </>
  );
}

function Section6({
  data,
  set,
}: {
  data: FormData;
  set: (k: keyof FormData, v: FormData[keyof FormData]) => void;
}) {
  return (
    <>
      <FieldTextarea
        label="Additional Details"
        value={data.additionalInfo}
        onChange={(v) => set("additionalInfo", v)}
        placeholder="Any additional context, constraints, or requests that didn't fit elsewhere..."
        rows={6}
      />
    </>
  );
}

function SuccessScreen() {
  return (
    <div className="min-h-screen bg-black flex flex-col items-center justify-center px-6 text-center">
      <div className="w-20 h-20 rounded-full bg-[#DC4436] flex items-center justify-center mb-8">
        <Check size={40} className="text-white" />
      </div>
      <h1 className="text-5xl font-black text-white mb-4 tracking-tight">
        Form Submitted!
      </h1>
      <p className="text-gray-400 text-base max-w-sm leading-relaxed">
        Thank you for submitting your intake form. The BUILD UMass team will
        review your project and get back to you soon.
      </p>
    </div>
  );
}

export function IntakeForm() {
  const [section, setSection] = useState(0);
  const [submitted, setSubmitted] = useState(false);
  const [formData, setFormData] = useState<FormData>(initialFormData);
  const cardRef = useRef<HTMLDivElement>(null);

  // Auto-save every 60s
  useEffect(() => {
    const interval = setInterval(() => {
      console.log("Auto-saved draft", new Date().toISOString());
    }, 60000);
    return () => clearInterval(interval);
  }, [formData]);

  const set = (k: keyof FormData, v: FormData[keyof FormData]) =>
    setFormData((prev) => ({ ...prev, [k]: v }));

  const goTo = (i: number) => {
    setSection(i);
    cardRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (submitted) return <SuccessScreen />;

  const sections = [
    <Section1 key={0} data={formData} set={set} />,
    <Section2 key={1} data={formData} set={set} />,
    <Section3 key={2} data={formData} set={set} />,
    <Section4 key={3} data={formData} set={set} />,
    <Section5 key={4} data={formData} set={set} />,
    <Section6 key={5} data={formData} set={set} />,
  ];

  const isLast = section === SECTION_TITLES.length - 1;

  return (
    <div className="h-screen overflow-hidden bg-black flex flex-col items-center px-4 pt-10">
      <div className="w-full max-w-[480px] flex flex-col pb-8">
        {/* Section title */}
        <h1
          className="text-4xl font-black text-white mb-5 tracking-tight leading-tight flex-shrink-0"
          style={{ fontFamily: "'Inter', sans-serif" }}
        >
          {SECTION_TITLES[section]}
        </h1>

        {/* Form card — sizes to content, scrolls when it overflows */}
        <div
          ref={cardRef}
          className="bg-[#1e1e1e] rounded-2xl px-6 py-6 overflow-y-auto"
          style={{ maxHeight: "calc(100vh - 220px)" }}
        >
          {sections[section]}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-center gap-3 mt-6">
          <button
            type="button"
            onClick={() => section > 0 && goTo(section - 1)}
            disabled={section === 0}
            className="w-11 h-11 rounded-full bg-[#DC4436] flex items-center justify-center text-white transition-opacity disabled:opacity-30 hover:opacity-90 flex-shrink-0"
          >
            <ChevronLeft size={22} />
          </button>

          <div className="flex items-center gap-2">
            {SECTION_TITLES.map((_, i) => (
              <button
                key={i}
                type="button"
                onClick={() => goTo(i)}
                className={`rounded-full transition-all ${
                  i === section
                    ? "w-3 h-3 bg-[#DC4436]"
                    : "w-2.5 h-2.5 bg-transparent border border-white/60 hover:border-white"
                }`}
              />
            ))}
          </div>

          {isLast ? (
            <button
              type="button"
              onClick={() => setSubmitted(true)}
              className="h-11 px-6 rounded-full bg-[#DC4436] flex items-center gap-2 text-white text-sm font-semibold transition-opacity hover:opacity-90 flex-shrink-0"
            >
              Submit
              <Check size={16} />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => goTo(section + 1)}
              className="w-11 h-11 rounded-full bg-[#DC4436] flex items-center justify-center text-white transition-opacity hover:opacity-90 flex-shrink-0"
            >
              <ChevronRight size={22} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
