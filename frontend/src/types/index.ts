export interface Message {
  id: string;
  role: 'user' | 'agent' | 'meta';
  content: string;
  timestamp: Date;
}

export interface StartSessionRequest {
  first_name?: string;
  last_name?: string;
  phone: string;
  dob?: string;
}

export interface StartSessionResponse {
  session_id: string;
  messages: Array<{ role: string; content: string }>;
  audio_b64?: string | null;
}

export interface TurnRequest {
  session_id: string;
  user_input: string;
}

export interface TurnResponse {
  agent_message: string;
  end_call: boolean;
  audio_b64?: string | null;
  user_transcript?: string | null;
}

export type SessionStatus = 'idle' | 'active' | 'thinking' | 'error' | 'ended';

export interface IntakeFormData {
  firstName: string;
  lastName: string;
  phone: string;
  dobMonth: string;
  dobDay: string;
  dobYear: string;
  isReturning: boolean;
}

export interface SessionState {
  sessionId: string | null;
  messages: Message[];
  status: SessionStatus;
  isAgentResponding: boolean;
  agentVoiceEnabled: boolean;
  callEnded: boolean;
}
