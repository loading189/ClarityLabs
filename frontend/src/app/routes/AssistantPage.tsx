import PageHeader from "../../components/common/PageHeader";
import AssistantPage from "../../features/assistant/AssistantPage";

export default function AssistantRoutePage() {
  return (
    <div>
      <PageHeader
        title="Summary"
        subtitle="Recent changes across signals and actions, with links to evidence and work."
      />
      <AssistantPage />
    </div>
  );
}
