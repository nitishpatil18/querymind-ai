import "node:module";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
const backend = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";
var vite_config_default = defineConfig({
	plugins: [react(), tailwindcss()],
	server: {
		port: 5173,
		proxy: {
			"/api": {
				target: backend,
				changeOrigin: true
			},
			"/health": {
				target: backend,
				changeOrigin: true
			}
		}
	},
	test: {
		environment: "jsdom",
		globals: true,
		setupFiles: ["./src/setupTests.ts"],
		css: false
	}
});
export { vite_config_default as default };

//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoidml0ZS5jb25maWcuanMiLCJuYW1lcyI6W10sInNvdXJjZXMiOlsiL3Nlc3Npb25zL3Jjdy0wMTR6Y3I1dnh2bnlpbmh6ZG5tc21ycm4vbW50L3F1ZXJ5bWluZC1haS9mcm9udGVuZC92aXRlLmNvbmZpZy50cyJdLCJzb3VyY2VzQ29udGVudCI6WyIvLy8gPHJlZmVyZW5jZSB0eXBlcz1cInZpdGVzdC9jb25maWdcIiAvPlxuaW1wb3J0IHRhaWx3aW5kY3NzIGZyb20gXCJAdGFpbHdpbmRjc3Mvdml0ZVwiO1xuaW1wb3J0IHJlYWN0IGZyb20gXCJAdml0ZWpzL3BsdWdpbi1yZWFjdFwiO1xuaW1wb3J0IHsgZGVmaW5lQ29uZmlnIH0gZnJvbSBcInZpdGVcIjtcblxuY29uc3QgYmFja2VuZCA9IHByb2Nlc3MuZW52LlZJVEVfQkFDS0VORF9VUkwgPz8gXCJodHRwOi8vbG9jYWxob3N0OjgwMDBcIjtcblxuZXhwb3J0IGRlZmF1bHQgZGVmaW5lQ29uZmlnKHtcbiAgcGx1Z2luczogW3JlYWN0KCksIHRhaWx3aW5kY3NzKCldLFxuICBzZXJ2ZXI6IHtcbiAgICBwb3J0OiA1MTczLFxuICAgIHByb3h5OiB7XG4gICAgICBcIi9hcGlcIjogeyB0YXJnZXQ6IGJhY2tlbmQsIGNoYW5nZU9yaWdpbjogdHJ1ZSB9LFxuICAgICAgXCIvaGVhbHRoXCI6IHsgdGFyZ2V0OiBiYWNrZW5kLCBjaGFuZ2VPcmlnaW46IHRydWUgfSxcbiAgICB9LFxuICB9LFxuICB0ZXN0OiB7XG4gICAgZW52aXJvbm1lbnQ6IFwianNkb21cIixcbiAgICBnbG9iYWxzOiB0cnVlLFxuICAgIHNldHVwRmlsZXM6IFtcIi4vc3JjL3NldHVwVGVzdHMudHNcIl0sXG4gICAgY3NzOiBmYWxzZSxcbiAgfSxcbn0pO1xuIl0sIm1hcHBpbmdzIjoiOzs7O0FBS0EsTUFBTSxVQUFVLFFBQVEsSUFBSSxvQkFBb0I7QUFFaEQsSUFBQSxzQkFBZSxhQUFhO0NBQzFCLFNBQVMsQ0FBQyxNQUFNLEdBQUcsWUFBWSxDQUFDO0NBQ2hDLFFBQVE7RUFDTixNQUFNO0VBQ04sT0FBTztHQUNMLFFBQVE7SUFBRSxRQUFRO0lBQVMsY0FBYztHQUFLO0dBQzlDLFdBQVc7SUFBRSxRQUFRO0lBQVMsY0FBYztHQUFLO0VBQ25EO0NBQ0Y7Q0FDQSxNQUFNO0VBQ0osYUFBYTtFQUNiLFNBQVM7RUFDVCxZQUFZLENBQUMscUJBQXFCO0VBQ2xDLEtBQUs7Q0FDUDtBQUNGLENBQUMifQ==