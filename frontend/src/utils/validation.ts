import type { IntakeFormData } from '../types';

export function validatePhone(phone: string): boolean {
  // Remove all non-digits
  const digits = phone.replace(/\D/g, '');
  // Valid if 10 digits (US) or 11 starting with 1
  return digits.length === 10 || (digits.length === 11 && digits[0] === '1');
}

export function formatPhone(phone: string): string {
  const digits = phone.replace(/\D/g, '');
  if (digits.length === 0) return '';
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 10)}`;
}

export function validateDOB(month: string, day: string, year: string): boolean {
  // All fields are required
  if (!month || !day || !year) return false;

  const m = parseInt(month, 10);
  const d = parseInt(day, 10);
  const y = parseInt(year, 10);

  if (isNaN(m) || isNaN(d) || isNaN(y)) return false;
  if (m < 1 || m > 12) return false;
  if (d < 1 || d > 31) return false;
  if (y < 1900 || y > new Date().getFullYear()) return false;

  // Check valid date
  const date = new Date(y, m - 1, d);
  return (
    date.getFullYear() === y &&
    date.getMonth() === m - 1 &&
    date.getDate() === d
  );
}

export function formatDOBForAPI(month: string, day: string, year: string): string | undefined {
  if (!month || !day || !year) return undefined;
  const m = month.padStart(2, '0');
  const d = day.padStart(2, '0');
  return `${year}-${m}-${d}`;
}

export function isFormValid(data: IntakeFormData): boolean {
  // Phone is always required
  if (!validatePhone(data.phone)) return false;

  if (data.isReturning) {
    // Returning patient only needs phone
    return true;
  }

  // New patient needs first name, last name, phone, and DOB
  if (!data.firstName.trim() || !data.lastName.trim()) return false;

  // DOB is required for new patients
  if (!validateDOB(data.dobMonth, data.dobDay, data.dobYear)) return false;

  return true;
}
