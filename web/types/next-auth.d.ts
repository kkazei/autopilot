import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session { login?: string }
}
declare module "next-auth/jwt" {
  interface JWT { login?: string }
}
