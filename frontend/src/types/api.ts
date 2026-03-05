export type Priority = 'low' | 'medium' | 'high';

export interface Todo {
  id: string;
  title: string;
  description: string | null;
  completed: boolean;
  priority: Priority;
  due_date: string | null;
  user_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface TodoListResponse {
  todos: Todo[];
  total: number;
}

export interface CreateTodoRequest {
  title: string;
  description?: string | null;
  priority?: Priority;
  due_date?: string | null;
}

export interface UpdateTodoRequest {
  title?: string;
  description?: string | null;
  completed?: boolean;
  priority?: Priority;
  due_date?: string | null;
}

export interface TodoStats {
  total: number;
  completed: number;
  pending: number;
  high_priority: number;
}

export interface CurrentUser {
  email: string | null;
  name: string | null;
  display_name: string;
  is_authenticated: boolean;
}

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
}
