import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { analytics } from "@/api";

export default function PrivacySettings() {
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["analytics-consent"],
    queryFn: analytics.getConsent,
  });

  const mutation = useMutation({
    mutationFn: (consent) => analytics.setConsent(consent),
    onSuccess: (_, consent) => {
      queryClient.invalidateQueries({ queryKey: ["analytics-consent"] });
      toast.success(consent ? "Analytics enabled" : "Analytics disabled");
    },
    onError: () => toast.error("Failed to update analytics preference"),
  });

  const consent = data?.consent ?? false;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-txt mb-1">Privacy &amp; Analytics</h2>
        <p className="text-sm text-txt-muted">
          When enabled, anonymous usage events (logins, note creates, AI requests) are recorded to
          help improve WorldStitch. No note content or message bodies are ever stored.
        </p>
      </div>

      <div className="flex items-center justify-between p-4 bg-elevated rounded-xl border border-border-subtle">
        <div>
          <p className="text-sm font-medium text-txt">Share usage analytics</p>
          <p className="text-xs text-txt-muted mt-0.5">
            Event types, timestamps, and AI request counts only — never content.
          </p>
        </div>
        <button
          disabled={isLoading || mutation.isPending}
          onClick={() => mutation.mutate(!consent)}
          className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
            consent ? "bg-accent" : "bg-gray-300"
          } disabled:opacity-50`}
          role="switch"
          aria-checked={consent}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ${
              consent ? "translate-x-5" : "translate-x-0"
            }`}
          />
        </button>
      </div>

      <p className="text-xs text-txt-muted">
        You can change this setting at any time. Disabling analytics takes effect immediately.
      </p>
    </div>
  );
}
