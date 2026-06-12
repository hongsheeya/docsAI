import { OnInit } from '@angular/core';
import { Service } from '@wiz/libs/portal/season/service';

export class Component implements OnInit {
    constructor(public service: Service) { }

    public loading: boolean = false;

    public data: any = {
        username: '',
        email: '',
        name: '',
        password: '',
        password_confirm: ''
    };

    public async ngOnInit() {
        await this.service.init();
        let check = await this.service.auth.check();
        if (check) return location.href = "/doc/write";
    }

    public async alert(message: string, status: string = 'error') {
        return await this.service.modal.show({
            title: "",
            message: message,
            cancel: false,
            actionBtn: status,
            action: '확인',
            status: status
        });
    }

    public async signup() {
        if (this.loading) return;

        let d = this.data;

        // 유효성 검사
        if (!d.username || d.username.length < 4) {
            await this.alert("아이디는 4자 이상 입력해주세요.");
            return;
        }
        if (!/^[a-zA-Z0-9_]+$/.test(d.username)) {
            await this.alert("아이디는 영문, 숫자, 밑줄(_)만 사용할 수 있습니다.");
            return;
        }
        if (!d.email || !d.email.includes('@')) {
            await this.alert("올바른 이메일 주소를 입력해주세요.");
            return;
        }
        if (!d.name) {
            await this.alert("이름을 입력해주세요.");
            return;
        }
        if (!d.password || d.password.length < 8) {
            await this.alert("비밀번호는 8자 이상 입력해주세요.");
            return;
        }
        if (d.password !== d.password_confirm) {
            await this.alert("비밀번호가 일치하지 않습니다.");
            return;
        }

        this.loading = true;
        await this.service.render();

        try {
            let { code, data } = await wiz.call("signup", {
                username: d.username,
                email: d.email,
                name: d.name,
                password: d.password
            });

            if (code == 200) {
                await this.alert("회원가입이 완료되었습니다. 로그인해주세요.", "success");
                this.service.href('/access');
            } else {
                await this.alert(data.message || "회원가입에 실패했습니다.", 'error');
            }
        } catch (e: any) {
            await this.alert("오류가 발생했습니다. 다시 시도해주세요.", 'error');
        }

        this.loading = false;
        await this.service.render();
    }
}
