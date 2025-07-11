// frontend/src/utils/time.js

/**
 * Parses an ISO 8601 string into a JavaScript Date object.
 * Relies on the backend always providing a string with a 'Z' suffix,
 * which ensures new Date() correctly interprets it as UTC.
 * @param {string | null | undefined} isoString - The ISO string from the API (e.g., "2025-06-23T14:00:00.000Z")
 * @returns {Date | null} A Date object or null if the input is invalid.
 */
export const parseISOString = (isoString) => {
  if (!isoString) return null;
  const date = new Date(isoString);
  return isNaN(date) ? null : date;
};

/**
 * Formats a Date object for a <input type="datetime-local">,
 * guaranteeing the displayed time matches the UTC parts of the Date.
 * This is the robust way to defeat browser-local timezone conversions, which
 * was the cause of the UI showing the wrong time (e.g., 8 AM instead of 14:00).
 * @param {Date | null} date - The JavaScript Date object.
 * @returns {string} A string in "YYYY-MM-DDTHH:mm:ss" format.
 */
export const formatForInput = (date) => {
  if (!date || isNaN(date)) return '';

  const pad = (num) => num.toString().padStart(2, '0');

  // Use getUTC* methods exclusively to ignore the browser's local timezone
  const year = date.getUTCFullYear();
  const month = pad(date.getUTCMonth() + 1); // getUTCMonth() is 0-indexed
  const day = pad(date.getUTCDate());
  const hours = pad(date.getUTCHours());
  const minutes = pad(date.getUTCMinutes());
  const seconds = pad(date.getUTCSeconds());

  return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
};