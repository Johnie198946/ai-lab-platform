export const restoreTaskMessages = (history = []) =>
  history.map((message) => ({
    ...message,
    failed: message.event_metadata?.terminal_type === "error",
  }));
