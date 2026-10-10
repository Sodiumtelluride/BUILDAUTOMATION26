"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronLeft, ChevronRight, Upload, X } from "lucide-react";
import {
  CONTENT_OPTIONS,
  CONTENT_PARTIAL,
  CONTENT_UPLOAD_RULES,
  CONTENT_YES,
  DOMAIN_OPTIONS,
  DOMAIN_OWNED,
  FEATURE_OPTIONS,
  INTEGRATION_OPTIONS,
  LOGO_OPTIONS,
  LOGO_UPLOAD,
  LOGO_UPLOAD_RULES,
  MAX_TONES,
  ORGANIZATION_TYPES,
  PAGE_OPTIONS,
  PRIMARY_GOALS,
  TONE_OPTIONS,
  checkFiles,
  validateSection,
  type FormErrors,
  type IntakeFormData,
} from "./validation";

const SECTION_TITLES = [
  "Organization & Contact",
  "Project Goals",
  "Design & Branding",
  "Content",
  "Technical Details",
  "Additional Information",
];

const initialFormData: IntakeFormData = {
  sensitiveDataAcknowledged: false,
  organizationName: "",
  primaryContactName: "",
  primaryContactEmail: "",
  organizationType: "",
  primaryGoal: "",
  organizationDescription: "",
  targetAudience: "",
  pages: [],
  features: [],
  featureDetails: "",
  hasLogo: "",
  logoFile: null,
  brandColors: "",
  brandFonts: "",
  visualStyle: "",
  referenceWebsites: ["", "", ""],
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

type SetField = <K extends keyof IntakeFormData>(key: K, value: IntakeFormData[K]) => void;

type SectionProps = {
  data: IntakeFormData;
  set: SetField;
  errors: FormErrors;
  setFieldError: (key: string, message: string | null) => void;
};

// "referenceWebsites.0" -> "referenceWebsites-0" (valid, stable DOM id)
const fieldId = (key: string) => key.replace(/\./g, "-");

const inputClass = (hasError: boolean) =>
  `w-full bg-white text-gray-900 rounded-xl px-4 py-3 text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#DC4436] ${
    hasError ? "ring-2 ring-[#DC4436]" : ""
  }`;

// ---------- Shared field pieces ----------

function FieldLabel({
  htmlFor,
  id,
  label,
  required,
}: {
  htmlFor?: string;
  id?: string;
  label: string;
  required?: boolean;
}) {
  return (
    <label
      htmlFor={htmlFor}
      id={id}
      className="block text-white text-sm font-medium mb-2 leading-snug"
    >
      {label}
      {required && (
        <span className="text-[#DC4436]" aria-hidden="true">
          {" "}
          *
        </span>
      )}
    </label>
  );
}

function FieldHint({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <p id={id} className="text-xs text-gray-400 mt-1 leading-snug">
      {children}
    </p>
  );
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="text-xs text-[#FF7A6E] mt-1.5 leading-snug">
      {message}
    </p>
  );
}

function describedBy(...ids: (string | false | undefined)[]) {
  const joined = ids.filter(Boolean).join(" ");
  return joined || undefined;
}

function FieldInput({
  name,
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  required,
  maxLength,
  hint,
  error,
}: {
  name: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  required?: boolean;
  maxLength?: number;
  hint?: string;
  error?: string;
}) {
  const id = fieldId(name);
  return (
    <div className="mb-5">
      <FieldLabel htmlFor={id} label={label} required={required} />
      <input
        id={id}
        type={type}
        value={value}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-required={required || undefined}
        aria-invalid={!!error || undefined}
        aria-describedby={describedBy(hint && `${id}-hint`, error && `${id}-error`)}
        className={inputClass(!!error)}
      />
      {hint && <FieldHint id={`${id}-hint`}>{hint}</FieldHint>}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

function FieldTextarea({
  name,
  label,
  value,
  onChange,
  placeholder,
  rows = 4,
  minLength,
  maxLength,
  required,
  hint,
  error,
}: {
  name: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  minLength?: number;
  maxLength?: number;
  required?: boolean;
  hint?: string;
  error?: string;
}) {
  const id = fieldId(name);
  return (
    <div className="mb-5">
      <FieldLabel htmlFor={id} label={label} required={required} />
      <textarea
        id={id}
        value={value}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        aria-required={required || undefined}
        aria-invalid={!!error || undefined}
        aria-describedby={describedBy(hint && `${id}-hint`, error && `${id}-error`)}
        className={`${inputClass(!!error)} resize-none`}
      />
      <div className="flex justify-between gap-3">
        <div>
          {hint && <FieldHint id={`${id}-hint`}>{hint}</FieldHint>}
          <FieldError id={`${id}-error`} message={error} />
        </div>
        {maxLength && (
          <p className="text-xs text-gray-500 mt-1 flex-shrink-0">
            {minLength && value.trim().length < minLength
              ? `${value.trim().length}/${minLength} min`
              : `${value.length}/${maxLength}`}
          </p>
        )}
      </div>
    </div>
  );
}

function FieldSelect({
  name,
  label,
  value,
  onChange,
  options,
  required,
  hint,
  error,
}: {
  name: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  required?: boolean;
  hint?: string;
  error?: string;
}) {
  const id = fieldId(name);
  return (
    <div className="mb-5">
      <FieldLabel htmlFor={id} label={label} required={required} />
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-required={required || undefined}
          aria-invalid={!!error || undefined}
          aria-describedby={describedBy(hint && `${id}-hint`, error && `${id}-error`)}
          className={`${inputClass(!!error)} appearance-none cursor-pointer pr-10`}
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
      {hint && <FieldHint id={`${id}-hint`}>{hint}</FieldHint>}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

function FieldMultiSelect({
  name,
  label,
  options,
  selected,
  onChange,
  max,
  required,
  hint,
  error,
}: {
  name: string;
  label: string;
  options: string[];
  selected: string[];
  onChange: (v: string[]) => void;
  max?: number;
  required?: boolean;
  hint?: string;
  error?: string;
}) {
  const id = fieldId(name);
  const atMax = max !== undefined && selected.length >= max;
  const toggle = (opt: string) => {
    if (selected.includes(opt)) {
      onChange(selected.filter((s) => s !== opt));
    } else if (!atMax) {
      onChange([...selected, opt]);
    }
  };
  return (
    <div className="mb-5">
      <FieldLabel id={`${id}-label`} label={label} required={required} />
      <div
        id={id}
        role="group"
        tabIndex={-1}
        aria-labelledby={`${id}-label`}
        aria-describedby={describedBy(hint && `${id}-hint`, error && `${id}-error`)}
        className={`flex flex-wrap gap-2 rounded-xl focus:outline-none ${
          error ? "ring-2 ring-[#DC4436] ring-offset-4 ring-offset-[#1e1e1e]" : ""
        }`}
      >
        {options.map((opt) => {
          const isSelected = selected.includes(opt);
          const disabled = !isSelected && atMax;
          return (
            <button
              key={opt}
              type="button"
              onClick={() => toggle(opt)}
              aria-pressed={isSelected}
              disabled={disabled}
              className={`px-4 py-2 rounded-full border text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#DC4436] disabled:opacity-40 disabled:cursor-not-allowed ${
                isSelected
                  ? "bg-white text-black border-white"
                  : "bg-transparent text-white border-white/70 hover:border-white hover:bg-white/10"
              }`}
            >
              {opt}
            </button>
          );
        })}
      </div>
      {hint && <FieldHint id={`${id}-hint`}>{hint}</FieldHint>}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

function FieldFileUpload({
  name,
  label,
  rules,
  files,
  onFiles,
  required,
  hint,
  error,
  onError,
}: {
  name: string;
  label: string;
  rules: { extensions: string[]; maxSizeMB: number; maxFiles: number };
  files: File[];
  onFiles: (files: File[]) => void;
  required?: boolean;
  hint?: string;
  error?: string;
  onError: (message: string | null) => void;
}) {
  const id = fieldId(name);
  const fileRef = useRef<HTMLInputElement>(null);
  const multiple = rules.maxFiles > 1;

  const handleSelect = (list: FileList | null) => {
    if (!list || list.length === 0) return;
    const next = multiple ? [...files, ...Array.from(list)] : [list[0]];
    const problem = checkFiles(next, rules);
    if (problem) {
      onError(problem);
    } else {
      onError(null);
      onFiles(next);
    }
    // Let the same file be picked again after removing it.
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="mb-5">
      <FieldLabel htmlFor={id} label={label} required={required} />
      <button
        id={id}
        type="button"
        onClick={() => fileRef.current?.click()}
        aria-describedby={describedBy(`${id}-accept`, hint && `${id}-hint`, error && `${id}-error`)}
        className={`w-full border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center cursor-pointer hover:border-[#DC4436] focus:outline-none focus-visible:border-[#DC4436] transition-colors bg-[#2a2a2a] ${
          error ? "border-[#DC4436]" : "border-gray-600"
        }`}
      >
        <span className="mb-2 text-gray-400">
          <Upload size={28} aria-hidden="true" />
        </span>
        <span className="text-white text-sm text-center">
          {multiple ? "Choose files" : files.length ? "Replace file" : "Choose a file"}
        </span>
        <span id={`${id}-accept`} className="text-gray-500 text-xs text-center mt-1">
          {rules.extensions.join(", ")} · max {rules.maxSizeMB}MB
          {multiple ? ` each · up to ${rules.maxFiles} files` : ""}
        </span>
      </button>
      <input
        ref={fileRef}
        type="file"
        accept={rules.extensions.join(",")}
        multiple={multiple}
        className="hidden"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(e) => handleSelect(e.target.files)}
      />
      {files.length > 0 && (
        <ul className="mt-2 space-y-1">
          {files.map((f, i) => (
            <li
              key={`${f.name}-${i}`}
              className="flex items-center justify-between gap-2 text-sm text-white bg-[#2a2a2a] rounded-lg px-3 py-2"
            >
              <span className="truncate">{f.name}</span>
              <button
                type="button"
                onClick={() => onFiles(files.filter((_, j) => j !== i))}
                aria-label={`Remove ${f.name}`}
                className="text-gray-400 hover:text-white flex-shrink-0"
              >
                <X size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {hint && <FieldHint id={`${id}-hint`}>{hint}</FieldHint>}
      <FieldError id={`${id}-error`} message={error} />
    </div>
  );
}

// ---------- Sections ----------

function Section1({ data, set, errors }: SectionProps) {
  return (
    <>
      <div className="mb-6 rounded-xl border border-white/15 bg-[#2a2a2a] p-4">
        <p className="text-white text-sm font-semibold mb-1">Before you start</p>
        <p className="text-gray-300 text-sm leading-snug mb-3">
          Only share information about your organization. Do not upload or paste client
          records, health information, financial data, immigration documents, or any other
          confidential or legally protected material.
        </p>
        <label htmlFor="sensitiveDataAcknowledged" className="flex items-start gap-3 cursor-pointer">
          <input
            id="sensitiveDataAcknowledged"
            type="checkbox"
            checked={data.sensitiveDataAcknowledged}
            onChange={(e) => set("sensitiveDataAcknowledged", e.target.checked)}
            aria-required="true"
            aria-invalid={!!errors.sensitiveDataAcknowledged || undefined}
            aria-describedby={
              errors.sensitiveDataAcknowledged ? "sensitiveDataAcknowledged-error" : undefined
            }
            className="mt-0.5 h-4 w-4 flex-shrink-0 accent-[#DC4436] cursor-pointer"
          />
          <span className="text-white text-sm leading-snug">
            I understand and will not include confidential or protected information.
            <span className="text-[#DC4436]" aria-hidden="true">
              {" "}
              *
            </span>
          </span>
        </label>
        <FieldError
          id="sensitiveDataAcknowledged-error"
          message={errors.sensitiveDataAcknowledged}
        />
      </div>

      <FieldInput
        name="organizationName"
        label="Organization Name"
        required
        maxLength={100}
        value={data.organizationName}
        onChange={(v) => set("organizationName", v)}
        placeholder="e.g., BUILD UMass"
        hint="Your organization's full legal or official name. This appears on your website."
        error={errors.organizationName}
      />
      <FieldInput
        name="primaryContactName"
        label="Primary Contact Name"
        required
        maxLength={100}
        value={data.primaryContactName}
        onChange={(v) => set("primaryContactName", v)}
        placeholder="e.g., John Smith"
        hint="Who BUILD should talk to about this project. Not shown on the site."
        error={errors.primaryContactName}
      />
      <FieldInput
        name="primaryContactEmail"
        label="Primary Contact Email"
        required
        type="email"
        value={data.primaryContactEmail}
        onChange={(v) => set("primaryContactEmail", v)}
        placeholder="e.g., johnsmith@email.com"
        hint="We'll send your confirmation, preview link, and final site here."
        error={errors.primaryContactEmail}
      />
      <FieldSelect
        name="organizationType"
        label="Organization Type"
        required
        value={data.organizationType}
        onChange={(v) => set("organizationType", v)}
        options={ORGANIZATION_TYPES}
        error={errors.organizationType}
      />
    </>
  );
}

function Section2({ data, set, errors }: SectionProps) {
  const needsFeatureDetails = data.features.includes("Other");
  return (
    <>
      <FieldSelect
        name="primaryGoal"
        label="What is the primary goal of your website?"
        required
        value={data.primaryGoal}
        onChange={(v) => set("primaryGoal", v)}
        options={PRIMARY_GOALS}
        error={errors.primaryGoal}
      />
      <FieldTextarea
        name="organizationDescription"
        label="Describe your organization and what you do."
        required
        minLength={50}
        maxLength={1000}
        value={data.organizationDescription}
        onChange={(v) => set("organizationDescription", v)}
        placeholder="BUILD UMass is a student-run organization that is committed to providing nonprofits, startups, and local businesses with scalable technology..."
        hint="2–5 sentences, as if explaining to someone who has never heard of you."
        error={errors.organizationDescription}
      />
      <FieldTextarea
        name="targetAudience"
        label="Who is your target audience?"
        required
        minLength={30}
        maxLength={500}
        value={data.targetAudience}
        onChange={(v) => set("targetAudience", v)}
        placeholder="Local families with young children, mostly first-time visitors looking for weekend programs..."
        hint="Describe the people you want visiting your site: age range, background, or other relevant details."
        error={errors.targetAudience}
      />
      <FieldMultiSelect
        name="pages"
        label="What pages do you need on your site?"
        required
        options={PAGE_OPTIONS}
        selected={data.pages}
        onChange={(v) => set("pages", v)}
        error={errors.pages}
      />
      <FieldMultiSelect
        name="features"
        label="Which specific features do you need?"
        options={FEATURE_OPTIONS}
        selected={data.features}
        onChange={(v) => set("features", v)}
        error={errors.features}
      />
      <FieldTextarea
        name="featureDetails"
        label="Feature details"
        required={needsFeatureDetails}
        maxLength={500}
        rows={3}
        value={data.featureDetails}
        onChange={(v) => set("featureDetails", v)}
        placeholder="Anything else we should know about the features you need..."
        hint={needsFeatureDetails ? "Required because you selected \"Other\"." : undefined}
        error={errors.featureDetails}
      />
    </>
  );
}

function Section3({ data, set, errors, setFieldError }: SectionProps) {
  const showLogoUpload = data.hasLogo === LOGO_UPLOAD;
  return (
    <>
      <FieldSelect
        name="hasLogo"
        label="Do you have an existing logo?"
        required
        value={data.hasLogo}
        onChange={(v) => set("hasLogo", v)}
        options={LOGO_OPTIONS}
        hint={
          data.hasLogo === "No — I will provide one later"
            ? "We'll build your site with a placeholder logo. It can't go live until you send us your logo."
            : undefined
        }
        error={errors.hasLogo}
      />
      {showLogoUpload && (
        <FieldFileUpload
          name="logoFile"
          label="Upload your logo"
          required
          rules={LOGO_UPLOAD_RULES}
          files={data.logoFile ? [data.logoFile] : []}
          onFiles={(files) => set("logoFile", files[0] ?? null)}
          hint="SVG or PNG with a transparent background works best. Use the highest resolution you have."
          error={errors.logoFile}
          onError={(msg) => setFieldError("logoFile", msg)}
        />
      )}
      <FieldInput
        name="brandColors"
        label="Brand Colors"
        value={data.brandColors}
        onChange={(v) => set("brandColors", v)}
        placeholder="e.g., #1A3C6E, #C9A84C, white"
        hint="Hex codes, color names, or a plain description. Leave blank and we'll choose."
        error={errors.brandColors}
      />
      <FieldInput
        name="brandFonts"
        label="Brand Fonts"
        maxLength={200}
        value={data.brandFonts}
        onChange={(v) => set("brandFonts", v)}
        placeholder="e.g., primary: Sans, secondary: Arial"
        hint="Leave blank and we'll choose fonts that fit."
        error={errors.brandFonts}
      />
      <FieldTextarea
        name="visualStyle"
        label="Describe the visual style you want"
        required
        minLength={30}
        maxLength={500}
        value={data.visualStyle}
        onChange={(v) => set("visualStyle", v)}
        placeholder="Clean and professional with a modern feel. We want it to look credible and established."
        hint="Plain language is perfect. No technical terms needed."
        error={errors.visualStyle}
      />
      <div className="mb-5">
        <FieldLabel id="referenceWebsites-label" label="Reference websites you like (up to 3)" />
        {data.referenceWebsites.map((url, i) => {
          const key = `referenceWebsites.${i}`;
          const id = fieldId(key);
          return (
            <div key={i} className="mb-2">
              <div className="flex items-center gap-2">
                <input
                  id={id}
                  type="text"
                  inputMode="url"
                  value={url}
                  onChange={(e) => {
                    const updated = [...data.referenceWebsites];
                    updated[i] = e.target.value;
                    set("referenceWebsites", updated);
                    setFieldError(key, null);
                  }}
                  placeholder="example.com"
                  aria-labelledby="referenceWebsites-label"
                  aria-invalid={!!errors[key] || undefined}
                  aria-describedby={errors[key] ? `${id}-error` : undefined}
                  className={`flex-1 ${inputClass(!!errors[key])}`}
                />
                <button
                  type="button"
                  onClick={() => {
                    const updated = [...data.referenceWebsites];
                    updated[i] = "";
                    set("referenceWebsites", updated);
                    setFieldError(key, null);
                  }}
                  aria-label={`Clear reference website ${i + 1}`}
                  className="text-gray-500 hover:text-white transition-colors flex-shrink-0"
                >
                  <X size={18} />
                </button>
              </div>
              <FieldError id={`${id}-error`} message={errors[key]} />
            </div>
          );
        })}
      </div>
    </>
  );
}

function Section4({ data, set, errors, setFieldError }: SectionProps) {
  const hasSomeContent = data.hasContent === CONTENT_YES || data.hasContent === CONTENT_PARTIAL;
  return (
    <>
      <FieldSelect
        name="hasContent"
        label="Do you have existing written content for your site?"
        required
        value={data.hasContent}
        onChange={(v) => set("hasContent", v)}
        options={CONTENT_OPTIONS}
        hint={
          data.hasContent && !hasSomeContent
            ? "We'll write your copy from your answers. Please review it carefully when we send the preview."
            : undefined
        }
        error={errors.hasContent}
      />
      {hasSomeContent && (
        <>
          <FieldTextarea
            name="existingContent"
            label="Paste your existing content"
            required
            maxLength={5000}
            value={data.existingContent}
            onChange={(v) => set("existingContent", v)}
            placeholder="Paste any text you want used or referenced..."
            hint="This can be rough. It will be edited and formatted."
            error={errors.existingContent}
          />
          <FieldFileUpload
            name="contentFiles"
            label="Upload content documents"
            rules={CONTENT_UPLOAD_RULES}
            files={data.contentFiles}
            onFiles={(files) => set("contentFiles", files)}
            error={errors.contentFiles}
            onError={(msg) => setFieldError("contentFiles", msg)}
          />
        </>
      )}
      <FieldMultiSelect
        name="toneAndVoice"
        label="Tone and Voice"
        required
        max={MAX_TONES}
        options={TONE_OPTIONS}
        selected={data.toneAndVoice}
        onChange={(v) => set("toneAndVoice", v)}
        hint={`Choose up to ${MAX_TONES}.`}
        error={errors.toneAndVoice}
      />
      <FieldTextarea
        name="contentRestrictions"
        label="Is there any content we should avoid?"
        maxLength={500}
        value={data.contentRestrictions}
        onChange={(v) => set("contentRestrictions", v)}
        placeholder="e.g., Don't mention specific donor names. Avoid religious language."
        hint="Any topics, phrases, claims, or approaches to avoid."
        error={errors.contentRestrictions}
      />
    </>
  );
}

function Section5({ data, set, errors }: SectionProps) {
  const ownsDomain = data.hasDomain === DOMAIN_OWNED;
  return (
    <>
      <FieldSelect
        name="hasDomain"
        label="Do you have a domain name?"
        required
        value={data.hasDomain}
        onChange={(v) => set("hasDomain", v)}
        options={DOMAIN_OPTIONS}
        hint={
          data.hasDomain && !ownsDomain
            ? "We'll launch on a BUILD subdomain (yourorg.buildumass.org). A custom domain can be connected later."
            : undefined
        }
        error={errors.hasDomain}
      />
      {ownsDomain && (
        <FieldInput
          name="domainName"
          label="Domain Name"
          required
          value={data.domainName}
          onChange={(v) => set("domainName", v)}
          placeholder="example.org"
          hint="Just the domain, without http:// or www."
          error={errors.domainName}
        />
      )}
      <FieldMultiSelect
        name="integrations"
        label="What third-party tools do you need to connect to your site?"
        options={INTEGRATION_OPTIONS}
        selected={data.integrations}
        onChange={(v) => set("integrations", v)}
        error={errors.integrations}
      />
      <FieldTextarea
        name="integrationDetails"
        label="Integration Details"
        maxLength={500}
        value={data.integrationDetails}
        onChange={(v) => set("integrationDetails", v)}
        placeholder="Account IDs, embed codes, integration notes..."
        hint="Leave blank and BUILD will follow up."
        error={errors.integrationDetails}
      />
    </>
  );
}

function Section6({ data, set, errors }: SectionProps) {
  return (
    <FieldTextarea
      name="additionalInfo"
      label="Additional Details"
      maxLength={1000}
      rows={6}
      value={data.additionalInfo}
      onChange={(v) => set("additionalInfo", v)}
      placeholder="Any additional context, constraints, or requests that didn't fit elsewhere..."
      error={errors.additionalInfo}
    />
  );
}

const SECTIONS = [Section1, Section2, Section3, Section4, Section5, Section6];

function SuccessScreen() {
  return (
    <div className="min-h-screen bg-black flex flex-col items-center justify-center px-6 text-center">
      <div className="w-20 h-20 rounded-full bg-[#DC4436] flex items-center justify-center mb-8">
        <Check size={40} className="text-white" aria-hidden="true" />
      </div>
      <h1 className="text-5xl font-black text-white mb-4 tracking-tight">Form Submitted!</h1>
      <p className="text-gray-400 text-base max-w-sm leading-relaxed">
        Thank you for submitting your intake form. The BUILD UMass team will review your
        project and get back to you soon.
      </p>
    </div>
  );
}

// ---------- Form ----------

export function IntakeForm() {
  const [section, setSection] = useState(0);
  const [submitted, setSubmitted] = useState(false);
  const [formData, setFormData] = useState<IntakeFormData>(initialFormData);
  const [errors, setErrors] = useState<FormErrors>({});
  // Bumped whenever validation fails, so we move focus to the first bad field.
  const [focusRequest, setFocusRequest] = useState(0);
  const cardRef = useRef<HTMLDivElement>(null);

  // TODO(next PR): auto-save drafts every 60s and "Save and continue later"
  // (PRD 2.1). Needs a backend endpoint, so it isn't implemented here yet.

  useEffect(() => {
    if (focusRequest === 0) return;
    const firstKey = Object.keys(errors)[0];
    if (firstKey) document.getElementById(fieldId(firstKey))?.focus();
    // Only run when a new focus request is made, not on every error change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusRequest]);

  const set: SetField = (key, value) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key as string];
      return next;
    });
  };

  const setFieldError = (key: string, message: string | null) => {
    setErrors((prev) => {
      const next = { ...prev };
      if (message) next[key] = message;
      else delete next[key];
      return next;
    });
  };

  const goTo = (i: number) => {
    setSection(i);
    cardRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Moving backward is always allowed. Moving forward validates every
  // section in between and stops at the first one with problems.
  const navigateTo = (target: number) => {
    if (target <= section) {
      setErrors({});
      goTo(target);
      return;
    }
    for (let s = section; s < target; s++) {
      const sectionErrors = validateSection(s, formData);
      if (Object.keys(sectionErrors).length > 0) {
        setErrors(sectionErrors);
        if (s !== section) goTo(s);
        setFocusRequest((n) => n + 1);
        return;
      }
    }
    setErrors({});
    goTo(target);
  };

  const handleSubmit = () => {
    for (let s = 0; s < SECTION_TITLES.length; s++) {
      const sectionErrors = validateSection(s, formData);
      if (Object.keys(sectionErrors).length > 0) {
        setErrors(sectionErrors);
        if (s !== section) goTo(s);
        setFocusRequest((n) => n + 1);
        return;
      }
    }
    // TODO(next PR): POST to /api/intake once the field schema is agreed with backend.
    setSubmitted(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (submitted) return <SuccessScreen />;

  const CurrentSection = SECTIONS[section];
  const isLast = section === SECTION_TITLES.length - 1;
  const errorCount = Object.keys(errors).length;

  return (
    <div className="h-screen overflow-hidden bg-black flex flex-col items-center px-4 pt-10">
      <div className="w-full max-w-[480px] flex flex-col pb-8">
        <p className="text-gray-400 text-sm mb-1">
          Step {section + 1} of {SECTION_TITLES.length}
        </p>
        <h1 className="text-4xl font-black text-white mb-5 tracking-tight leading-tight flex-shrink-0">
          {SECTION_TITLES[section]}
        </h1>

        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            if (isLast) handleSubmit();
            else navigateTo(section + 1);
          }}
        >
          <div
            ref={cardRef}
            className="bg-[#1e1e1e] rounded-2xl px-6 py-6 overflow-y-auto"
            style={{ maxHeight: "calc(100vh - 250px)" }}
          >
            <p className="text-xs text-gray-400 mb-5">
              Fields marked <span className="text-[#DC4436]">*</span> are required.
            </p>
            <CurrentSection
              data={formData}
              set={set}
              errors={errors}
              setFieldError={setFieldError}
            />
          </div>

          <p role="alert" className="text-center text-sm text-[#FF7A6E] mt-4 min-h-5">
            {errorCount > 0
              ? `Please fix ${errorCount === 1 ? "1 field" : `${errorCount} fields`} above to continue.`
              : ""}
          </p>

          <div className="flex items-center justify-center gap-3 mt-2">
            <button
              type="button"
              onClick={() => section > 0 && navigateTo(section - 1)}
              disabled={section === 0}
              aria-label="Previous section"
              className="w-11 h-11 rounded-full bg-[#DC4436] flex items-center justify-center text-white transition-opacity disabled:opacity-30 hover:opacity-90 flex-shrink-0"
            >
              <ChevronLeft size={22} />
            </button>

            <div className="flex items-center gap-2">
              {SECTION_TITLES.map((title, i) => (
                <button
                  key={title}
                  type="button"
                  onClick={() => navigateTo(i)}
                  aria-label={`Go to section ${i + 1}: ${title}`}
                  aria-current={i === section ? "step" : undefined}
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
                type="submit"
                className="h-11 px-6 rounded-full bg-[#DC4436] flex items-center gap-2 text-white text-sm font-semibold transition-opacity hover:opacity-90 flex-shrink-0"
              >
                Submit
                <Check size={16} aria-hidden="true" />
              </button>
            ) : (
              <button
                type="submit"
                aria-label="Next section"
                className="w-11 h-11 rounded-full bg-[#DC4436] flex items-center justify-center text-white transition-opacity hover:opacity-90 flex-shrink-0"
              >
                <ChevronRight size={22} />
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
