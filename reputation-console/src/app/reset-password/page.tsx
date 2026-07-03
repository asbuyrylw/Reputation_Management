import { SetPasswordCard } from "@/components/SetPasswordCard";

export default function ResetPasswordPage() {
  return (
    <SetPasswordCard
      endpoint="/auth/reset-password"
      title="Reset your password"
      cta="Reset password"
      errorMsg="This reset link is invalid or expired. Request a new one."
    />
  );
}
