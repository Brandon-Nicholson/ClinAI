import type {
  StartSessionRequest,
  StartSessionResponse,
  TurnRequest,
  TurnResponse,
} from '../types';

const API_BASE = '';

export async function startSession(
  data: StartSessionRequest
): Promise<StartSessionResponse> {
  const response = await fetch(`${API_BASE}/start_session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error(
        'Patient not found. Please register with your full information.'
      );
    }
    throw new Error(`Failed to start session: ${response.status}`);
  }

  return response.json();
}

export async function sendTurn(data: TurnRequest): Promise<TurnResponse> {
  const response = await fetch(`${API_BASE}/turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`Turn failed: ${response.status}`);
  }

  return response.json();
}

export async function sendVoiceTurn(
  sessionId: string,
  audioBlob: Blob
): Promise<TurnResponse> {
  const formData = new FormData();
  formData.append('session_id', sessionId);
  formData.append('audio', audioBlob, 'audio.webm');

  const response = await fetch(`${API_BASE}/voice_turn`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Voice turn failed: ${response.status}`);
  }

  return response.json();
}
