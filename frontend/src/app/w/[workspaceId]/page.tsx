import { redirect } from "next/navigation";

export default async function WorkspaceIndex(props: PageProps<"/w/[workspaceId]">) {
  const { workspaceId } = await props.params;
  redirect(`/w/${workspaceId}/documents`);
}
