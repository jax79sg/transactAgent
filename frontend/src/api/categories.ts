import { apiRequest } from "./client";
import type { CategoryDTO } from "./types";

export function listCategories(): Promise<CategoryDTO[]> {
  return apiRequest<CategoryDTO[]>("/categories");
}

export function addCategory(name: string): Promise<CategoryDTO> {
  return apiRequest<CategoryDTO>("/categories", { method: "POST", body: { name } });
}

export function renameCategory(categoryId: string, name: string): Promise<CategoryDTO> {
  return apiRequest<CategoryDTO>(`/categories/${categoryId}`, { method: "PUT", body: { name } });
}

export function removeCategory(categoryId: string): Promise<void> {
  return apiRequest<void>(`/categories/${categoryId}`, { method: "DELETE" });
}
