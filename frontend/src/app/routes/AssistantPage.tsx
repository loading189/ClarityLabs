import PageHeader from "../../components/common/PageHeader";
import AssistantPage from "../../features/assistant/AssistantPage";

export default function AssistantRoutePage() {
  return (
    <div>
      <PageHeader
        title="Assistant"
        subtitle="Summarize live alerts and inspect deterministic signal explanations."
      />
      <AssistantPage />
    </div>
  );
}
