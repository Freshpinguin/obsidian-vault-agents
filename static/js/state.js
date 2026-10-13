// Globaler Anwendungszustand
export const state = {
  sessionId: null,
  isSending: false,
  currentFile: null,
  currentFileRawContent: "",
  currentFileAiSummary: "",
  viewMode: "rendered", // 'rendered' oder 'raw'
  vaultTreeData: null,
  expandedFolders: new Set(),
  isSavingFile: false,
  isDeletingFile: false,
  isRequestingSummary: false,
};
