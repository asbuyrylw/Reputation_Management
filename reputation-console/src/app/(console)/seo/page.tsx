"use client";

import { useBusiness } from "@/lib/business";
import { useSiteAudit } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import { SiteAuditView } from "@/components/SiteAuditView";

export default function SeoPage() {
  const { businessId } = useBusiness();
  const { data, isLoading } = useSiteAudit(businessId);

  if (isLoading) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="SEO / site audit"
        subtitle="The technical and content health of your own website, from the latest crawl — what to fix, page by page."
      />
      {!data ? (
        <Card>
          <p className="text-sm text-slate-600">No site audit yet — it runs as part of a full audit.</p>
        </Card>
      ) : (
        <>
          <div className="mb-3 text-xs text-slate-400">As of {new Date(data.created_at).toLocaleDateString()}</div>
          <SiteAuditView summary={data.summary} />
        </>
      )}
    </div>
  );
}
