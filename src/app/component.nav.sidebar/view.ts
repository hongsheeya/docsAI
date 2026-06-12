import { OnInit } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';

export class Component implements OnInit {
    constructor(public service: Service) { }

    public isLoggedIn: boolean = false;
    public isAdmin: boolean = false;
    public showUserMenu: boolean = false;

    public navItems = [
        { link: '/doc/write', label: '워크스페이스', icon: 'home' },
        { link: '/doc/templates', label: '양식', icon: 'doc' }
    ];

    public async ngOnInit() {
        await this.service.init();
        let check = await this.service.auth.check();
        this.isLoggedIn = !!check;
        if (this.isLoggedIn) {
            this.isAdmin = this.service.auth.session?.role === 'admin';
        }
        await this.service.render();
    }

    public navigate(link: string) {
        this.service.href(link);
    }

    public isActive(link: string) {
        return location.pathname === link || location.pathname.startsWith(link + '/');
    }

    public navButtonClass(link: string) {
        if (this.isActive(link)) {
            return 'bg-teal-50 text-teal-700';
        }
        return 'text-slate-500 hover:bg-slate-50 hover:text-slate-700';
    }

    public async toggleUserMenu() {
        this.showUserMenu = !this.showUserMenu;
        await this.service.render();
    }

    public logout() {
        location.href = '/auth/logout?returnTo=/doc/write';
    }
}
