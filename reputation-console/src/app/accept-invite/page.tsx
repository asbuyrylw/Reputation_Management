import { SetPasswordCard } from "@/components/SetPasswordCard";

export default function AcceptInvitePage() {
  return (
    <SetPasswordCard
      endpoint="/auth/accept-invite"
      title="Set your password"
      cta="Activate account"
      errorMsg="This invite link is invalid or expired. Ask your admin to re-send it."
    />
  );
}
