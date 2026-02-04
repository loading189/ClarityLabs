import { useParams } from "react-router-dom";
import PageHeader from "../../components/common/PageHeader";
import SignalsCenter from "../../features/signals-center/SignalsCenter";
import { assertBusinessId } from "../../utils/businessId";

export default function SignalsCenterPage() {
  const { businessId: businessIdParam } = useParams();
  const businessId = assertBusinessId(businessIdParam, "SignalsCenterPage");

  if (!businessId) {
    return null;
  }

  return (
    <div>
      <PageHeader
        title="Signals Center"
        subtitle="Monitor, triage, and resolve continuous alerts for this business."
      />
      <SignalsCenter businessId={businessId} />
    </div>
  );
}
