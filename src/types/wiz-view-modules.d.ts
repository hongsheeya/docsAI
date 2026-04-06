declare module '@angular/core' {
    export interface OnInit {
        ngOnInit(): void | Promise<void>;
    }

    export interface OnDestroy {
        ngOnDestroy(): void;
    }

    export class ElementRef<T = any> {
        nativeElement: T;
    }

    export function HostListener(eventName: string, args?: string[]): any;
    export function ViewChild(selector: string, opts?: any): any;
}

declare module '@wiz/libs/portal/season/service' {
    export class Service {
        [key: string]: any;
    }
}
