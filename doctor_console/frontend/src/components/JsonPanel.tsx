type Props = {
  value: unknown;
  emptyLabel?: string;
};

export function JsonPanel({ value, emptyLabel = "No data saved for this section." }: Props) {
  if (value === null || value === undefined || value === "") {
    return <div className="empty-state">{emptyLabel}</div>;
  }
  return <pre className="json-panel">{JSON.stringify(value, null, 2)}</pre>;
}
