import React, { useState, useCallback } from 'react';
import { PatientToggle } from './PatientToggle';
import { DOBInput } from './DOBInput';
import type { IntakeFormData, StartSessionRequest } from '../../types';
import { isFormValid, formatPhone, formatDOBForAPI } from '../../utils/validation';

interface IntakeFormProps {
  onSubmit: (data: StartSessionRequest) => Promise<void>;
  disabled?: boolean;
}

export function IntakeForm({ onSubmit, disabled = false }: IntakeFormProps) {
  const [formData, setFormData] = useState<IntakeFormData>({
    firstName: '',
    lastName: '',
    phone: '',
    dobMonth: '',
    dobDay: '',
    dobYear: '',
    isReturning: false,
  });

  const [isSubmitting, setIsSubmitting] = useState(false);

  const updateField = useCallback(
    <K extends keyof IntakeFormData>(key: K, value: IntakeFormData[K]) => {
      setFormData((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  const handlePhoneChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const formatted = formatPhone(e.target.value);
      updateField('phone', formatted);
    },
    [updateField]
  );

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!isFormValid(formData) || isSubmitting || disabled) return;

      setIsSubmitting(true);

      const request: StartSessionRequest = {
        phone: formData.phone.replace(/\D/g, ''),
      };

      if (!formData.isReturning) {
        request.first_name = formData.firstName.trim();
        request.last_name = formData.lastName.trim();
        const dob = formatDOBForAPI(
          formData.dobMonth,
          formData.dobDay,
          formData.dobYear
        );
        if (dob) {
          request.dob = dob;
        }
      }

      try {
        await onSubmit(request);
      } finally {
        setIsSubmitting(false);
      }
    },
    [formData, onSubmit, isSubmitting, disabled]
  );

  const formValid = isFormValid(formData);
  const showNameFields = !formData.isReturning;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Patient Type Toggle */}
      <div className="pb-2">
        <PatientToggle
          isReturning={formData.isReturning}
          onChange={(val) => updateField('isReturning', val)}
          disabled={disabled}
        />
      </div>

      {/* Name Fields - Only for new patients */}
      {showNameFields && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="space-y-2">
            <label className="block text-xs font-medium text-clinai-text-dim uppercase tracking-wider">
              First Name
            </label>
            <input
              type="text"
              value={formData.firstName}
              onChange={(e) => updateField('firstName', e.target.value)}
              placeholder="Enter first name"
              disabled={disabled}
              className="input-field"
            />
          </div>
          <div className="space-y-2">
            <label className="block text-xs font-medium text-clinai-text-dim uppercase tracking-wider">
              Last Name
            </label>
            <input
              type="text"
              value={formData.lastName}
              onChange={(e) => updateField('lastName', e.target.value)}
              placeholder="Enter last name"
              disabled={disabled}
              className="input-field"
            />
          </div>
        </div>
      )}

      {/* DOB - Only for new patients */}
      {showNameFields && (
        <DOBInput
          month={formData.dobMonth}
          day={formData.dobDay}
          year={formData.dobYear}
          onMonthChange={(val) => updateField('dobMonth', val)}
          onDayChange={(val) => updateField('dobDay', val)}
          onYearChange={(val) => updateField('dobYear', val)}
          disabled={disabled}
        />
      )}

      {/* Phone - Always required */}
      <div className="space-y-2">
        <label className="block text-xs font-medium text-clinai-text-dim uppercase tracking-wider">
          Phone Number
        </label>
        <input
          type="tel"
          value={formData.phone}
          onChange={handlePhoneChange}
          placeholder="(555) 123-4567"
          disabled={disabled}
          className="input-field"
        />
      </div>

      {/* Hint Text */}
      <p className="text-sm text-clinai-text-dim">
        {formData.isReturning
          ? 'Enter your phone number to access your account.'
          : 'New patients: Please enter your information to get started.'}
      </p>

      {/* Submit Button */}
      <div className="pt-2">
        <button
        type="submit"
        disabled={!formValid || isSubmitting || disabled}
        className="btn-primary w-full sm:w-auto"
      >
        {isSubmitting ? (
          <span className="flex items-center justify-center gap-2">
            <svg
              className="animate-spin h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            Starting...
          </span>
        ) : (
          'Start Session'
        )}
        </button>
      </div>
    </form>
  );
}
