import React, { useEffect, useState } from 'react';

export default function ConditionNumberInput({ value, onChange, ...props }) {
  const [raw, setRaw] = useState(String(value ?? ''));
  useEffect(() => {
    if (raw !== value && Number(raw) !== value) setRaw(String(value ?? ''));
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  return <input {...props} value={raw} onChange={(event) => {
    const text = event.target.value;
    setRaw(text);
    onChange(text.trim() !== '' && Number.isFinite(Number(text)) ? Number(text) : text);
  }} />;
}
