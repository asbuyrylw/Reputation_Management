import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy — Reputation Console",
  description:
    "How Reputation Console collects, uses, stores, and protects your data, including data accessed from Google APIs.",
};

// Public, unauthenticated route (outside the (console) group) so it can be listed as the
// Privacy Policy URL on the Google OAuth consent screen. Static server component — no client
// state, no params. Effective date is editable; update the operator name + contact email below.
const OPERATOR = "Reputation Console";
const CONTACT_EMAIL = "logan@nexgenixai.com";
const EFFECTIVE = "August 14, 2026";

export default function PrivacyPolicyPage() {
  return (
    <main className="privacy-doc">
      <style>{`
        .privacy-doc {
          max-width: 46rem;
          margin: 0 auto;
          padding: 3.5rem 1.5rem 6rem;
          font-family: var(--font-inter), ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
          color: #1e2530;
          line-height: 1.65;
          font-size: 1rem;
        }
        .privacy-doc h1 {
          font-family: var(--font-fraunces), Georgia, serif;
          font-size: 2rem;
          font-weight: 600;
          letter-spacing: -0.01em;
          margin: 0 0 0.25rem;
        }
        .privacy-doc .eyebrow {
          font-family: var(--font-plex), ui-monospace, SFMono-Regular, Menlo, monospace;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          font-size: 0.72rem;
          color: #6b7280;
          margin: 0 0 1.5rem;
        }
        .privacy-doc h2 {
          font-family: var(--font-fraunces), Georgia, serif;
          font-size: 1.25rem;
          font-weight: 600;
          margin: 2.25rem 0 0.6rem;
          color: #111827;
        }
        .privacy-doc h3 { font-size: 1rem; font-weight: 600; margin: 1.25rem 0 0.4rem; }
        .privacy-doc p, .privacy-doc li { color: #374151; }
        .privacy-doc ul { padding-left: 1.25rem; margin: 0.5rem 0; }
        .privacy-doc li { margin: 0.3rem 0; }
        .privacy-doc a { color: #2563eb; text-decoration: underline; }
        .privacy-doc .lead { font-size: 1.05rem; color: #374151; }
        .privacy-doc .callout {
          border: 1px solid #dbe3ef; background: #f5f8ff; border-radius: 12px;
          padding: 1rem 1.15rem; margin: 1rem 0;
        }
        .privacy-doc code { font-family: var(--font-plex), ui-monospace, monospace; font-size: 0.85em; }
        .privacy-doc hr { border: none; border-top: 1px solid #e5e7eb; margin: 2.5rem 0; }
        .privacy-doc footer { margin-top: 2.5rem; font-size: 0.85rem; color: #6b7280; }
      `}</style>

      <p className="eyebrow">{OPERATOR}</p>
      <h1>Privacy Policy</h1>
      <p className="lead">Effective {EFFECTIVE}</p>

      <p>
        {OPERATOR} (&ldquo;we,&rdquo; &ldquo;us,&rdquo; or the &ldquo;Service&rdquo;) is a reputation- and
        search-visibility management platform. Businesses use it to audit how they appear across AI
        answer engines and search, plan and produce content, and — when they choose to connect them —
        pull performance data from their own accounts on services like Google Analytics and Google
        Search Console. This policy explains what data we collect, how we use and protect it, and the
        choices you have. It applies to data we access from Google APIs as described below.
      </p>

      <h2>1. Information we collect</h2>
      <ul>
        <li>
          <strong>Account information</strong> — the name and email address you use to sign in, and your
          role within an organization.
        </li>
        <li>
          <strong>Business and content data you provide</strong> — the business profiles, websites,
          uploaded source material, and content you create or manage in the Service.
        </li>
        <li>
          <strong>Data from accounts you connect</strong> — when you authorize an integration, we access
          data from that account solely to power the features you requested. This includes Google
          services (see Section 2), and may include WordPress and social-publishing platforms you connect.
        </li>
        <li>
          <strong>Operational data</strong> — basic logs and usage records needed to run, secure, and
          debug the Service.
        </li>
      </ul>

      <h2>2. Google user data</h2>
      <p>
        If you connect a Google account, we request only the access needed for the specific feature, using
        Google&rsquo;s standard OAuth consent flow. The scopes we may request, and why, are:
      </p>
      <ul>
        <li>
          <strong>Google Analytics</strong> (<code>analytics.readonly</code>) — read-only access to your
          GA4 properties to display sessions, engagement, conversions, and related metrics inside the
          Service.
        </li>
        <li>
          <strong>Google Search Console</strong> (<code>webmasters</code>, <code>siteverification</code>) —
          to read your search performance (clicks, impressions, position) and, only when you use the
          in-app &ldquo;verify a site&rdquo; assist, to verify and register a property you own.
        </li>
        <li>
          <strong>Google Business Profile</strong> — to read and, with your approval, help manage your
          business listing and reviews.
        </li>
        <li>
          <strong>YouTube</strong> — only if you choose to publish a video you have created and approved.
        </li>
      </ul>
      <p>
        We use Google user data <strong>only to provide and improve the features you use</strong> within
        the Service for the business you connected it to. We do <strong>not</strong> sell it, use it for
        advertising, or use it to train generalized AI/ML models. We only share it with the limited
        service providers needed to operate the Service (Section 4), or when required by law.
      </p>
      <div className="callout">
        <p style={{ margin: 0 }}>
          {OPERATOR}&rsquo;s use and transfer of information received from Google APIs to any other app
          will adhere to the{" "}
          <a href="https://developers.google.com/terms/api-services-user-data-policy" rel="noreferrer">
            Google API Services User Data Policy
          </a>
          , including the Limited Use requirements.
        </p>
      </div>

      <h2>3. How we use information</h2>
      <ul>
        <li>To provide the audits, analytics, content, and reporting features you request.</li>
        <li>To secure, maintain, and improve the Service and troubleshoot problems.</li>
        <li>To communicate with you about your account, notifications you enable, and support.</li>
      </ul>
      <p>We do not sell your personal information or your connected-account data.</p>

      <h2>4. How we store and share data</h2>
      <ul>
        <li>
          <strong>Security.</strong> Connection credentials and OAuth tokens are encrypted at rest, and
          access is restricted to the systems that need them to run the features you enabled.
        </li>
        <li>
          <strong>Service providers.</strong> We use a small set of subprocessors to run the Service —
          for example, cloud hosting and database providers, and AI providers used to generate content at
          your request. They may process data only to provide their service to us and are bound by
          confidentiality and data-protection obligations. Google user data is not sent to AI providers
          for model training.
        </li>
        <li>
          <strong>No sale, no ads.</strong> We never sell your data and never use connected-account data
          for advertising.
        </li>
      </ul>

      <h2>5. Data retention and deletion</h2>
      <p>
        We keep data for as long as your account is active or as needed to provide the Service. You can{" "}
        <strong>disconnect any integration at any time</strong> from the Integrations page, which revokes
        our stored access token for that account. You may also revoke our access directly from your Google
        Account at{" "}
        <a href="https://myaccount.google.com/permissions" rel="noreferrer">
          myaccount.google.com/permissions
        </a>
        . To request deletion of your account and associated data, contact us at the address below and we
        will delete it within a reasonable period, except where retention is required by law.
      </p>

      <h2>6. Your choices and rights</h2>
      <ul>
        <li>Access, correct, or delete your account information.</li>
        <li>Connect or disconnect any integration at any time.</li>
        <li>Revoke Google access from your Google Account&rsquo;s permissions page.</li>
        <li>Contact us to exercise applicable data-protection rights.</li>
      </ul>

      <h2>7. Children&rsquo;s privacy</h2>
      <p>The Service is intended for businesses and is not directed to children under 13.</p>

      <h2>8. Changes to this policy</h2>
      <p>
        We may update this policy from time to time. When we make material changes, we will revise the
        effective date above and, where appropriate, notify you within the Service.
      </p>

      <h2>9. Contact us</h2>
      <p>
        Questions about this policy or your data? Email us at{" "}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>

      <hr />
      <footer>
        © 2026 {OPERATOR}. This page describes how the Service handles data,
        including data accessed via Google APIs, and is provided as the Privacy Policy referenced on our
        Google OAuth consent screen.
      </footer>
    </main>
  );
}
