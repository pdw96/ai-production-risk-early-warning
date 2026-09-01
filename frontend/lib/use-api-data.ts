"use client";

import { useEffect, useState } from "react";

interface ApiDataState<DataT> {
  data: DataT | null;
  error_message: string | null;
  is_loading: boolean;
}

export function use_api_data<DataT>(loader: () => Promise<DataT>): ApiDataState<DataT> {
  const [data, set_data] = useState<DataT | null>(null);
  const [error_message, set_error_message] = useState<string | null>(null);
  const [is_loading, set_is_loading] = useState(true);

  useEffect(() => {
    let is_current = true;

    async function load_data(): Promise<void> {
      set_is_loading(true);
      set_error_message(null);

      try {
        const response = await loader();
        if (is_current) {
          set_data(response);
        }
      } catch (error: unknown) {
        if (is_current) {
          set_error_message(
            error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.",
          );
        }
      } finally {
        if (is_current) {
          set_is_loading(false);
        }
      }
    }

    void load_data();
    return () => {
      is_current = false;
    };
  }, [loader]);

  return { data, error_message, is_loading };
}
