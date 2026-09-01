export interface Citation {
    id: string;
    database: string;
    label: string;
    url?: string;
}
export declare function toolDatabase(tool: string): string;
export declare function mergeCitation(citations: Citation[], tool: string, url?: string): Citation[];
